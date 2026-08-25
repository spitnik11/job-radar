"""Answer-tier trust rules (deterministic, no model needed): the user's library always wins, and a
sensitive legal/eligibility question is never machine-answered — it returns None so it stays a
review blocker rather than being guessed."""

from app.apply import answers
from app.apply_kit import ApplicationKit


def test_answer_library_wins():
    kit = ApplicationKit(answer_library={"current company": "Freelance"})
    assert answers.answer(kit, "What is your current company?") == "Freelance"


def test_sensitive_questions_never_guessed():
    kit = ApplicationKit()                        # empty library, so no library answer
    for q in ["Will you require visa sponsorship?",
              "Are you subject to any employment agreements or non-compete?",
              "Have you ever been convicted of a felony?",
              "Are you legally authorized to work in the US?"]:
        assert answers.answer(kit, q) is None, q


def test_sensitive_still_honors_explicit_library_answer():
    # if the USER pre-answered a sensitive question, that's their explicit choice — use it.
    kit = ApplicationKit(answer_library={"felony": "No"})
    assert answers.answer(kit, "Have you ever been convicted of a felony?") == "No"


def test_best_option_matching():
    opts = ["Eastern Time (US)", "Western Europe", "Outside this range"]
    assert answers._best_option("Eastern Time (US)", opts) == "Eastern Time (US)"
    assert answers._best_option("I am based in Eastern Time", opts) == "Eastern Time (US)"
    assert answers._best_option("Antarctica", opts) is None


def test_answer_choice_library_wins_and_maps_to_option():
    kit = ApplicationKit(answer_library={"time zone": "Eastern"})
    opts = ["I'm in the Eastern Time zone", "I'm in Europe", "Other"]
    assert answers.answer_choice(kit, "Which time zone are you in?", opts) == "I'm in the Eastern Time zone"


def test_answer_choice_never_picks_for_sensitive():
    kit = ApplicationKit()
    opts = ["Yes", "No"]
    assert answers.answer_choice(kit, "Are you legally authorized to work in the US?", opts) is None


def test_resolve_leaves_required_unanswered_as_open():
    kit = ApplicationKit()
    plan = {"filled": [], "open": [
        {"label": "Are you authorized to work in the US?", "type": "text", "required": True, "options": []}]}
    _, still_open = answers.resolve(kit, plan)
    assert len(still_open) == 1 and still_open[0]["required"]
