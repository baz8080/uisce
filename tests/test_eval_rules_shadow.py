from uisce.eval_rules_shadow import compare, fields_of


def llm(source="scheduled_end_with_time", date="2026-05-09", time="18:00",
        recurrence="none"):
    return {"end_source": source, "local_date": date, "local_time": time,
            "recurrence": recurrence}


def rules(source="scheduled_end_with_time", date="2026-05-09", time="18:00"):
    return {"end_source": source, "local_date": date, "local_time": time}


def test_abstain_when_rules_return_none():
    assert compare(llm(), None) == "abstain"


def test_agree_on_identical_fields():
    assert compare(llm(), rules()) == "agree"


def test_disagree_on_any_field():
    assert compare(llm(), rules(time="18:30")) == "disagree"
    assert compare(llm(), rules(date="2026-05-10")) == "disagree"
    assert compare(llm(), rules(source="completion_update")) == "disagree"


def test_llm_recurrence_is_never_agreement():
    # Even matching fields count against the rules here: the rules answer
    # would drop the window the site expands.
    assert compare(llm(recurrence="daily"), rules()) == "recurrence"


def test_times_compare_at_minute_precision():
    assert fields_of(llm(time="18:00:00")) == fields_of(rules(time="18:00"))
