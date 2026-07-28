import json
import threading
from benchmarks import run_bonsai_page_evaluation as runner
from types import SimpleNamespace
from pathlib import Path

import pytest
from benchmarks import evaluate_models


def test_together_model_registration_uses_exact_hosted_bonsai_id() -> None:
    config = evaluate_models.MODELS["bonsai_27b_together_page_pipeline"]

    assert config.model_id == "Prism-ML/Ternary-Bonsai-27B"
    assert config.provider == "PrismML/Together/PagePipeline"


def test_split_ocr_pages_returns_each_page_once_without_overlap() -> None:
    transcript = """# Page 1

alpha

# Page 2

beta

# Page 3

gamma
"""

    pages = runner.split_ocr_pages(transcript)

    assert [(page.number, page.text) for page in pages] == [
        (1, "# Page 1\n\nalpha\n"),
        (2, "# Page 2\n\nbeta\n"),
        (3, "# Page 3\n\ngamma\n"),
    ]
    assert sum(page.text.count("alpha") for page in pages) == 1
    assert sum(page.text.count("beta") for page in pages) == 1
    assert sum(page.text.count("gamma") for page in pages) == 1


def test_public_contract_builds_compact_strict_page_rows() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")

    assert contract.output_key == "records"
    assert contract.identity_fields["record"] == ("license_number",)
    assert set(contract.required_fields["record"]) == {
        "accidents_last_5_years",
        "date_hired",
        "date_of_birth",
        "license_class",
        "license_number",
        "mvr_run_date",
        "mvr_violations",
        "name",
        "state_licensed",
        "years_experienced",
    }

    response_format = runner.page_response_format(contract)
    schema = response_format["json_schema"]["schema"]
    row = schema["properties"]["rows"]["items"]
    assert response_format["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["rows"]
    assert row["minItems"] == len(contract.required_fields["record"])
    assert row["maxItems"] == len(contract.required_fields["record"])
    assert row["prefixItems"][3]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert row["prefixItems"][7]["anyOf"] == [
        {"type": "integer"},
        {"type": "null"},
    ]


def test_generic_mvr_page_prompt_has_no_demo_specific_field_guidance() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    page = runner.Page(
        number=10,
        text=(
            "# Page 10\n"
            "Run 01/21/2026\n"
            "Accidents,0\n"
            "Moving violations,None\n"
        ),
    )

    prompt = runner.build_page_prompt(contract, page)

    assert "Driver MVR field rules:" not in prompt
    assert '"mvr_run_date": copy the date printed after "Run"' not in prompt
    assert '"date_hired": use only a date explicitly labeled as hired' not in prompt


def test_compact_page_rows_decode_to_named_candidates_and_omit_nulls() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")

    candidates = runner._validate_candidates(
        {
            "rows": [
                [
                    "05/02/2016",
                    "05/10/1978",
                    "A",
                    "LA J100 200 300",
                    "01/21/2026",
                    "Rosa Nguyen",
                    "LA",
                    20,
                    None,
                    None,
                ]
            ]
        },
        contract,
    )

    assert candidates == [
        {
            "date_hired": "05/02/2016",
            "date_of_birth": "05/10/1978",
            "license_class": "A",
            "license_number": "LA J100 200 300",
            "mvr_run_date": "01/21/2026",
            "name": "Rosa Nguyen",
            "state_licensed": "LA",
            "years_experienced": 20,
        }
    ]


def test_public_contract_supports_policy_record_types_without_ground_truth_values() -> None:
    contract = runner.contract_for_template("policy_multihop_bop")

    assert contract.output_key == "records"
    assert "bop_coverage_item" in contract.required_fields
    assert "policy_clause_item" in contract.required_fields
    assert contract.identity_fields["policy_form_item"] == (
        "policy_number",
        "form_number",
        "edition_date",
    )

    schema = runner.page_response_format(contract)["json_schema"]["schema"]
    assert schema["required"] == sorted(contract.required_fields)
    assert set(schema["properties"]) == set(contract.required_fields)
    for record_type, fields in contract.required_fields.items():
        row = schema["properties"][record_type]["items"]
        assert row["minItems"] == len(fields) - 1
        assert row["maxItems"] == len(fields) - 1


def test_public_contracts_cover_every_released_record_shape() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data" / "manifest.json").read_text())

    for instance in manifest["instances"]:
        contract = runner.contract_for_template(instance["template"])
        truth = json.loads(
            (root / "data" / "ground_truth" / f"{instance['id']}.json").read_text()
        )
        by_type: dict[str, set[str]] = {}
        for record in truth:
            record_type = str(record.get("record_type") or "record")
            fields = set(record) - {"record_id", "applies_to_record_id"}
            by_type.setdefault(record_type, set()).update(fields)

        assert set(contract.required_fields) == set(by_type), instance["id"]
        for record_type, fields in by_type.items():
            assert set(contract.required_fields[record_type]) == fields, (
                instance["id"],
                record_type,
            )
            assert set(contract.identity_fields[record_type]) <= fields


def test_page_pipeline_has_a_distinct_offline_scorer_key() -> None:
    config = evaluate_models.MODELS[runner.DEFAULT_MODEL_KEY]

    assert config.provider == "PrismML/PagePipeline"
    assert config.model_id == runner.DEFAULT_MODEL_ID


class _FakeCompletions:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _chat_response(content: str, *, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5),
    )


def test_constrained_client_retries_truncated_generation_then_returns_json() -> None:
    completions = _FakeCompletions(
        [
            _chat_response('{"candidates":[', finish_reason="length"),
            _chat_response('{"candidates":[]}'),
        ]
    )
    api = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    sleeps: list[float] = []
    client = runner.BonsaiClient(
        endpoint="http://127.0.0.1:8080/v1",
        model_id="bonsai",
        max_attempts=3,
        api=api,
        sleep=sleeps.append,
    )
    response_format = runner.page_response_format(
        runner.contract_for_template("driver_mvr_request_and_roster")
    )

    result = client.generate_json(
        prompt="extract this page",
        response_format=response_format,
    )

    assert result.payload == {"candidates": []}
    assert result.attempts == 2
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 5
    assert sleeps == [1.0]
    assert completions.requests[-1]["model"] == "bonsai"
    assert completions.requests[-1]["response_format"] == response_format
    assert completions.requests[-1]["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_client_passes_injected_api_key_to_openai_constructor(monkeypatch) -> None:
    import openai

    captured: dict = {}

    def build_api(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(openai, "OpenAI", build_api)

    runner.BonsaiClient(
        endpoint="https://example.invalid/v1",
        model_id="bonsai",
        api_key="hosted-secret",
    )

    assert captured["api_key"] == "hosted-secret"


def test_client_omits_request_extras_when_none() -> None:
    completions = _FakeCompletions([_chat_response('{"candidates":[]}')])
    api = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = runner.BonsaiClient(
        endpoint="https://example.invalid/v1",
        model_id="bonsai",
        api=api,
        request_extra_body=None,
    )

    client.generate_json(
        prompt="extract this page",
        response_format=runner.page_response_format(
            runner.contract_for_template("driver_mvr_request_and_roster")
        ),
    )

    assert "extra_body" not in completions.requests[0]


def test_constrained_client_stops_after_retry_limit() -> None:
    completions = _FakeCompletions(
        [
            _chat_response("", finish_reason="length"),
            _chat_response("", finish_reason="length"),
            _chat_response("", finish_reason="length"),
        ]
    )
    api = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = runner.BonsaiClient(
        endpoint="http://127.0.0.1:8080/v1",
        model_id="bonsai",
        max_attempts=3,
        api=api,
        sleep=lambda _delay: None,
    )

    with pytest.raises(runner.RetryableInferenceError, match="token limit"):
        client.generate_json(
            prompt="extract this page",
            response_format=runner.page_response_format(
                runner.contract_for_template("driver_mvr_request_and_roster")
            ),
        )


class _ObservingPageClient:
    def __init__(self, page_dir: Path) -> None:
        self.page_dir = page_dir
        self.calls = 0

    def generate_json(self, **_kwargs) -> runner.InferenceResult:
        self.calls += 1
        if self.calls == 2:
            first = self.page_dir / "page_0001.json"
            assert first.is_file()
            assert json.loads(first.read_text())["candidates"] == [
                {"license_number": "A-1", "name": "Alpha"}
            ]
        return runner.InferenceResult(
            payload={
                "candidates": [
                    {
                        "license_number": f"A-{self.calls}",
                        "name": "Alpha" if self.calls == 1 else "Beta",
                    }
                ]
            },
            attempts=1,
            prompt_tokens=10,
            completion_tokens=5,
        )


def test_page_results_and_events_are_flushed_before_the_document_finishes(
    tmp_path: Path,
) -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    page_dir = tmp_path / "pages" / "sample"
    client = _ObservingPageClient(page_dir)

    results = runner.extract_pages(
        sample="sample",
        pages=[
            runner.Page(1, "# Page 1\nAlpha"),
            runner.Page(2, "# Page 2\nBeta"),
        ],
        contract=contract,
        client=client,
        output_dir=tmp_path,
        resume=True,
    )

    assert [result["page_number"] for result in results] == [1, 2]
    assert client.calls == 2
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert [(event["type"], event["page_number"]) for event in events] == [
        ("page_complete", 1),
        ("page_complete", 2),
    ]


def test_independent_page_requests_can_run_concurrently_without_reordering_results(
    tmp_path: Path,
) -> None:
    class ParallelClient:
        def __init__(self) -> None:
            self.barrier = threading.Barrier(2)

        def generate_json(self, *, prompt, **_kwargs):
            page_number = 1 if "# Page 1" in prompt else 2
            self.barrier.wait(timeout=2)
            return runner.InferenceResult(
                payload={
                    "candidates": [
                        {"license_number": f"A-{page_number}"}
                    ]
                },
                attempts=1,
                prompt_tokens=10,
                completion_tokens=5,
            )

    results = runner.extract_pages(
        sample="sample",
        pages=[
            runner.Page(1, "# Page 1\nAlpha"),
            runner.Page(2, "# Page 2\nBeta"),
        ],
        contract=runner.contract_for_template(
            "driver_mvr_request_and_roster"
        ),
        client=ParallelClient(),
        output_dir=tmp_path,
        resume=False,
        page_workers=2,
    )

    assert [result["page_number"] for result in results] == [1, 2]
    assert all(
        (tmp_path / "pages" / "sample" / f"page_{number:04d}.json").is_file()
        for number in (1, 2)
    )


def test_page_extraction_resumes_from_a_matching_checkpoint(tmp_path: Path) -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    page = runner.Page(1, "# Page 1\nAlpha")
    page_dir = tmp_path / "pages" / "sample"
    page_dir.mkdir(parents=True)
    client = _ObservingPageClient(page_dir)
    request_fingerprint = runner._request_fingerprint(
        client=client,
        prompt=runner.build_page_prompt(contract, page),
        response_format=runner.page_response_format(contract),
    )
    checkpoint = runner.build_page_checkpoint(
        sample="sample",
        page=page,
        candidates=[{"license_number": "A-1", "name": "Alpha"}],
        attempts=1,
        prompt_tokens=10,
        completion_tokens=5,
        request_fingerprint=request_fingerprint,
    )
    (page_dir / "page_0001.json").write_text(json.dumps(checkpoint))

    results = runner.extract_pages(
        sample="sample",
        pages=[page],
        contract=contract,
        client=client,
        output_dir=tmp_path,
        resume=True,
    )

    assert results == [checkpoint]
    assert client.calls == 0


def test_page_resume_rejects_a_checkpoint_from_another_request_config(
    tmp_path: Path,
) -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    page = runner.Page(1, "# Page 1\nAlpha")
    page_dir = tmp_path / "pages" / "sample"
    page_dir.mkdir(parents=True)
    stale = runner.build_page_checkpoint(
        sample="sample",
        page=page,
        candidates=[{"license_number": "OLD"}],
        attempts=1,
        prompt_tokens=10,
        completion_tokens=5,
        request_fingerprint="stale-request",
        model_id="old-model",
        endpoint="https://old.example/v1",
    )
    (page_dir / "page_0001.json").write_text(json.dumps(stale))
    client = _ObservingPageClient(page_dir)
    client.model_id = "new-model"
    client.endpoint = "https://new.example/v1"
    client.request_extra_body = None

    results = runner.extract_pages(
        sample="sample",
        pages=[page],
        contract=contract,
        client=client,
        output_dir=tmp_path,
        resume=True,
    )

    assert client.calls == 1
    assert results[0]["candidates"] == [
        {"license_number": "A-1", "name": "Alpha"}
    ]
    assert results[0]["request_fingerprint"] != "stale-request"
    assert results[0]["model_id"] == "new-model"
    assert results[0]["endpoint"] == "https://new.example/v1"


def test_page_extraction_retries_a_simple_invalid_inference_result(
    tmp_path: Path,
) -> None:
    class InvalidThenValidClient:
        def __init__(self) -> None:
            self.calls = 0

        def generate_json(self, **_kwargs):
            self.calls += 1
            payload = (
                {"candidates": [{"invented_field": "bad"}]}
                if self.calls == 1
                else {"candidates": [{"license_number": "A-1"}]}
            )
            return runner.InferenceResult(
                payload=payload,
                attempts=1,
                prompt_tokens=10,
                completion_tokens=5,
            )

    client = InvalidThenValidClient()
    results = runner.extract_pages(
        sample="sample",
        pages=[runner.Page(1, "# Page 1\nAlpha")],
        contract=runner.contract_for_template("driver_mvr_request_and_roster"),
        client=client,
        output_dir=tmp_path,
        resume=False,
        sleep=lambda _delay: None,
    )

    assert client.calls == 2
    assert results[0]["candidates"] == [{"license_number": "A-1"}]
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert [event["type"] for event in events] == [
        "inference_retry",
        "page_complete",
    ]


def _complete_mvr(**overrides) -> dict:
    record = {
        "accidents_last_5_years": None,
        "date_hired": "01/01/2020",
        "date_of_birth": "01/02/1980",
        "license_class": "A",
        "license_number": "A-1",
        "mvr_run_date": "02/01/2026",
        "mvr_violations": None,
        "name": "Alpha Driver",
        "state_licensed": "MI",
        "years_experienced": 20,
    }
    record.update(overrides)
    return record


def test_collapse_passes_complete_records_and_merges_disjoint_fragments() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    reducer_calls: list[runner.CandidateGroup] = []

    records = runner.collapse_and_reconcile(
        page_results=[
            {
                "page_number": 1,
                "candidates": [_complete_mvr()],
            },
            {
                "page_number": 2,
                "candidates": [
                    {
                        "license_number": "B-2",
                        "name": "Beta Driver",
                        "date_of_birth": "02/03/1985",
                        "date_hired": "03/04/2021",
                        "license_class": "B",
                        "state_licensed": "OH",
                        "years_experienced": 10,
                    }
                ],
            },
            {
                "page_number": 3,
                "candidates": [
                    {
                        "license_number": "B-2",
                        "mvr_run_date": "04/05/2026",
                        "mvr_violations": None,
                        "accidents_last_5_years": None,
                    }
                ],
            },
        ],
        contract=contract,
        reduce_group=lambda group: reducer_calls.append(group) or {},
    )

    assert records == [
        _complete_mvr(),
        _complete_mvr(
            license_number="B-2",
            name="Beta Driver",
            date_of_birth="02/03/1985",
            date_hired="03/04/2021",
            license_class="B",
            state_licensed="OH",
            years_experienced=10,
            mvr_run_date="04/05/2026",
        ),
    ]
    assert reducer_calls == []


def test_collapse_fills_missing_nullable_fields_without_a_model_call() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    roster_record = _complete_mvr()
    roster_record.pop("accidents_last_5_years")
    roster_record.pop("mvr_violations")

    records = runner.collapse_and_reconcile(
        page_results=[
            {
                "page_number": 2,
                "candidates": [roster_record],
            }
        ],
        contract=contract,
        reduce_group=lambda _group: pytest.fail(
            "nullable defaults should not call Bonsai"
        ),
    )

    assert records == [_complete_mvr()]


def test_collapse_reconciles_one_conflicting_logical_record_without_batching() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    calls: list[runner.CandidateGroup] = []
    resolved = _complete_mvr(name="Resolved Driver")

    def reduce_one(group: runner.CandidateGroup) -> dict:
        calls.append(group)
        return resolved

    records = runner.collapse_and_reconcile(
        page_results=[
            {
                "page_number": 4,
                "candidates": [_complete_mvr(name="Alpha Driver")],
            },
            {
                "page_number": 9,
                "candidates": [
                    {
                        "license_number": "A-1",
                        "name": "A. Driver",
                    }
                ],
            },
        ],
        contract=contract,
        reduce_group=reduce_one,
    )

    assert records == [resolved]
    assert len(calls) == 1
    assert calls[0].pages == (4, 9)
    assert len(calls[0].fragments) == 2


def test_parallel_reconciliation_preserves_logical_record_order() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    barrier = threading.Barrier(2)

    def reduce_one(group: runner.CandidateGroup) -> dict:
        barrier.wait(timeout=2)
        return _complete_mvr(
            license_number=str(group.identity[1]),
            name=f"Resolved {group.identity[1]}",
        )

    records = runner.collapse_and_reconcile(
        page_results=[
            {
                "page_number": 1,
                "candidates": [_complete_mvr(license_number="A-1", name="Alpha")],
            },
            {
                "page_number": 2,
                "candidates": [
                    {"license_number": "A-1", "name": "Alternate Alpha"}
                ],
            },
            {
                "page_number": 3,
                "candidates": [_complete_mvr(license_number="B-2", name="Beta")],
            },
            {
                "page_number": 4,
                "candidates": [
                    {"license_number": "B-2", "name": "Alternate Beta"}
                ],
            },
        ],
        contract=contract,
        reduce_group=reduce_one,
        reduction_workers=2,
    )

    assert [record["license_number"] for record in records] == ["A-1", "B-2"]
    assert [record["name"] for record in records] == [
        "Resolved A-1",
        "Resolved B-2",
    ]


def test_collapse_removes_exact_duplicate_records_without_model_call() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    complete = _complete_mvr()

    records = runner.collapse_and_reconcile(
        page_results=[
            {"page_number": 1, "candidates": [complete]},
            {"page_number": 2, "candidates": [dict(complete)]},
        ],
        contract=contract,
        reduce_group=lambda _group: pytest.fail("duplicate should not call Bonsai"),
    )

    assert records == [complete]


def test_collapse_discards_candidates_without_the_public_identity_key() -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")

    records = runner.collapse_and_reconcile(
        page_results=[
            {
                "page_number": 1,
                "candidates": [
                    {
                        "license_number": "",
                        "license_class": "J100 200 300",
                        "state_licensed": "LA",
                    }
                ],
            }
        ],
        contract=contract,
        reduce_group=lambda _group: pytest.fail(
            "identity-free distractor should not call Bonsai"
        ),
    )

    assert records == []


class _ReducerClient:
    def __init__(
        self,
        record: dict,
        *,
        model_id: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.record = record
        self.model_id = model_id
        self.endpoint = endpoint
        self.request_extra_body = None
        self.prompts: list[str] = []
        self.response_formats: list[dict] = []

    def generate_json(self, *, prompt, response_format, **_kwargs):
        self.prompts.append(prompt)
        self.response_formats.append(response_format)
        return runner.InferenceResult(
            payload={"record": self.record},
            attempts=1,
            prompt_tokens=30,
            completion_tokens=12,
        )


def test_reduction_prompt_exposes_nested_record_shapes_to_the_model() -> None:
    contract = runner.contract_for_template("claim_crosspage_multihop")
    group = runner.CandidateGroup(
        record_type="record",
        identity=("record", "claim-1"),
        pages=(1,),
        fragments=(
            runner.CandidateFragment(1, {"claim_number": "claim-1"}),
        ),
        merged={"claim_number": "claim-1"},
        conflicts=(),
    )

    prompt = runner.build_reduction_prompt(
        group=group,
        contract=contract,
        pages_by_number={1: runner.Page(1, "# Page 1\nclaim evidence")},
    )

    schema_text = prompt.split(
        "Expected record JSON Schema:\n", 1
    )[1].split("\n\nCandidate fragments:", 1)[0]
    record_schema = json.loads(schema_text)
    assert record_schema["properties"]["bi"] == {
        "type": "object",
        "properties": {
            "reserve": {"type": "number"},
            "paid": {"type": "number"},
            "recovered": {"type": "number"},
            "total_incurred": {"type": "number"},
        },
        "required": ["reserve", "paid", "recovered", "total_incurred"],
        "additionalProperties": False,
    }


def test_reduce_one_group_uses_fragments_without_raw_page_bodies(
    tmp_path: Path,
) -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    group = runner.CandidateGroup(
        record_type="record",
        identity=("record", "A-1"),
        pages=(2, 7),
        fragments=(
            runner.CandidateFragment(2, {"license_number": "A-1", "name": "Alpha"}),
            runner.CandidateFragment(
                7,
                {"license_number": "A-1", "mvr_run_date": "02/01/2026"},
            ),
        ),
        merged={
            "license_number": "A-1",
            "name": "Alpha",
            "mvr_run_date": "02/01/2026",
        },
        conflicts=(),
    )
    final = _complete_mvr()
    client = _ReducerClient(final)

    record = runner.reduce_candidate_group(
        sample="sample",
        group=group,
        contract=contract,
        pages_by_number={
            2: runner.Page(2, "# Page 2\nroster evidence"),
            7: runner.Page(7, "# Page 7\nMVR evidence"),
        },
        client=client,
        output_dir=tmp_path,
        resume=True,
    )

    assert record == final
    assert "# Page 2\nroster evidence" not in client.prompts[0]
    assert "# Page 7\nMVR evidence" not in client.prompts[0]
    assert '"page_number": 2' in client.prompts[0]
    assert '"page_number": 7' in client.prompts[0]
    final_schema = client.response_formats[0]["json_schema"]["schema"][
        "properties"
    ]["record"]
    assert set(final_schema["required"]) == set(contract.required_fields["record"])
    checkpoints = list((tmp_path / "reductions" / "sample").glob("*.json"))
    assert len(checkpoints) == 1
    assert json.loads(checkpoints[0].read_text())["record"] == final
    assert json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])[
        "type"
    ] == "reduction_complete"


def test_reduction_resume_rejects_another_model_checkpoint(
    tmp_path: Path,
) -> None:
    contract = runner.contract_for_template("driver_mvr_request_and_roster")
    group = runner.CandidateGroup(
        record_type="record",
        identity=("record", "A-1"),
        pages=(1,),
        fragments=(
            runner.CandidateFragment(
                1, {"license_number": "A-1", "name": "Alpha"}
            ),
        ),
        merged={"license_number": "A-1", "name": "Alpha"},
        conflicts=(),
    )
    pages = {1: runner.Page(1, "# Page 1\nDriver evidence")}
    first_client = _ReducerClient(
        _complete_mvr(name="First Model"),
        model_id="model-a",
        endpoint="https://a.example/v1",
    )
    second_client = _ReducerClient(
        _complete_mvr(name="Second Model"),
        model_id="model-b",
        endpoint="https://b.example/v1",
    )

    runner.reduce_candidate_group(
        sample="sample",
        group=group,
        contract=contract,
        pages_by_number=pages,
        client=first_client,
        output_dir=tmp_path,
        resume=True,
    )
    second_record = runner.reduce_candidate_group(
        sample="sample",
        group=group,
        contract=contract,
        pages_by_number=pages,
        client=second_client,
        output_dir=tmp_path,
        resume=True,
    )

    assert second_record["name"] == "Second Model"
    assert len(second_client.prompts) == 1
    assert len(list((tmp_path / "reductions" / "sample").glob("*.json"))) == 2


def test_run_document_never_requires_ground_truth_during_extraction(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "data"
    (dataset_dir / "metadata").mkdir(parents=True)
    (dataset_dir / "transcripts" / "ocr_gemini").mkdir(parents=True)
    (dataset_dir / "metadata" / "sample.json").write_text(
        json.dumps(
            {
                "id": "sample",
                "template": "driver_mvr_request_and_roster",
            }
        )
    )
    (dataset_dir / "transcripts" / "ocr_gemini" / "sample.md").write_text(
        "# Page 1\nDriver evidence\n"
    )
    output_dir = tmp_path / "results"

    class DocumentClient:
        def generate_json(self, **_kwargs):
            return runner.InferenceResult(
                payload={"candidates": [_complete_mvr()]},
                attempts=1,
                prompt_tokens=10,
                completion_tokens=5,
            )

    metadata = runner.run_document(
        dataset_dir=dataset_dir,
        sample="sample",
        transcript="ocr",
        output_dir=output_dir,
        model_key=runner.DEFAULT_MODEL_KEY,
        client=DocumentClient(),
        resume=True,
    )

    prediction = output_dir / (
        f"sample_ocr_{runner.DEFAULT_MODEL_KEY}_predicted.json"
    )
    assert json.loads(prediction.read_text()) == [_complete_mvr()]
    assert metadata["predicted_count"] == 1
    assert not (dataset_dir / "ground_truth").exists()


def test_cli_defaults_to_resumable_three_attempt_inference() -> None:
    parser = runner.build_argument_parser()
    args = parser.parse_args(["--output-dir", "results"])

    assert "local Ternary" not in parser.description
    assert args.model_key == runner.DEFAULT_MODEL_KEY
    assert args.model == runner.DEFAULT_MODEL_ID
    assert args.endpoint == runner.DEFAULT_ENDPOINT
    assert args.timeout_seconds == 900
    assert args.page_workers == 1
    assert args.reduction_workers == 1
    assert args.api_key_env is None
    assert args.max_attempts == 3
    assert args.document_attempts == 2
    assert args.resume is True


def test_saved_prediction_report_is_labeled_as_saved_predictions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_calls: list[dict] = []
    monkeypatch.setattr(
        evaluate_models,
        "run_evaluation_from_saved_predictions",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        evaluate_models,
        "generate_report",
        lambda *_args, **kwargs: report_calls.append(kwargs),
    )

    runner.score_saved_predictions(
        models=[runner.DEFAULT_MODEL_KEY],
        samples=["sample"],
        transcript="ocr",
        dataset_dir=tmp_path,
        output_dir=tmp_path / "results",
    )

    assert report_calls == [{"evaluation_mode": "saved_predictions"}]


def test_sample_discovery_uses_public_manifest_without_reading_ground_truth(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "instances": [
                    {"id": "b", "template": "ifta_mileage_by_vehicle"},
                    {"id": "a", "template": "driver_mvr_request_and_roster"},
                ]
            }
        )
    )

    assert runner.discover_samples(tmp_path, requested=None) == ["a", "b"]
    assert runner.discover_samples(tmp_path, requested=["b"]) == ["b"]


def test_corpus_run_retries_failed_document_and_flushes_status(
    tmp_path: Path,
) -> None:
    attempts: dict[str, int] = {}

    def run_one(**kwargs):
        sample = kwargs["sample"]
        attempts[sample] = attempts.get(sample, 0) + 1
        if sample == "a" and attempts[sample] == 1:
            raise runner.RetryableInferenceError("temporary")
        return {
            "sample": sample,
            "predicted_count": 1,
            "extraction_time": 0.1,
        }

    statuses, metadata = runner.run_corpus(
        dataset_dir=tmp_path / "data",
        samples=["a", "b"],
        transcript="ocr",
        output_dir=tmp_path / "results",
        model_key=runner.DEFAULT_MODEL_KEY,
        client=type("Client", (), {"model_id": "hosted/bonsai"})(),
        resume=True,
        document_attempts=2,
        run_document_fn=run_one,
        sleep=lambda _delay: None,
    )

    assert statuses == [("a", 0), ("b", 0)]
    assert attempts == {"a": 2, "b": 1}
    assert set(metadata) == {"a", "b"}
    status_text = (tmp_path / "results" / "per_sample_status.tsv").read_text()
    assert status_text == "sample\tstatus\na\t0\nb\t0\n"
    run_state = json.loads((tmp_path / "results" / "run_metadata.json").read_text())
    assert run_state["sample_statuses"] == {"a": 0, "b": 0}
    assert run_state["model_id"] == "hosted/bonsai"


def test_main_scores_saved_predictions_after_successful_corpus_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset_dir = tmp_path / "data"
    dataset_dir.mkdir()
    (dataset_dir / "manifest.json").write_text(
        json.dumps({"instances": [{"id": "sample"}]})
    )
    output_dir = tmp_path / "results"
    scored: list[tuple[list[str], list[str]]] = []
    built_clients: list[dict] = []
    corpus_calls: list[dict] = []

    monkeypatch.setenv("TEST_HOSTED_KEY", "hosted-secret")
    monkeypatch.setattr(
        runner,
        "BonsaiClient",
        lambda **kwargs: built_clients.append(kwargs) or object(),
    )
    monkeypatch.setattr(
        runner,
        "run_corpus",
        lambda **kwargs: corpus_calls.append(kwargs)
        or ([("sample", 0)], {"sample": {}}),
    )
    monkeypatch.setattr(
        runner,
        "score_saved_predictions",
        lambda **kwargs: scored.append((kwargs["samples"], kwargs["models"])),
    )
    monkeypatch.setattr(runner, "_require_power_mode", lambda: None)

    exit_code = runner.main(
        [
            "--dataset-dir",
            str(dataset_dir),
            "--output-dir",
            str(output_dir),
            "--api-key-env",
            "TEST_HOSTED_KEY",
            "--reduction-workers",
            "4",
        ]
    )

    assert exit_code == 0
    assert built_clients[0]["api_key"] == "hosted-secret"
    assert corpus_calls[0]["reduction_workers"] == 4
    assert scored == [(["sample"], [runner.DEFAULT_MODEL_KEY])]
