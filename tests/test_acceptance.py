"""PRD 15.1 end to end, with a scripted LLM.

backend/scenario_check.py holds the scenario itself because it doubles as a demo that
prints the transcript. This runs the same thing under pytest so the gate cannot pass by
being forgotten.
"""
import asyncio
import importlib

from backend import scenario_check


def test_acceptance_scenario(capsys):
    # The module consumes its own SCRIPT list, so reload for a clean run.
    importlib.reload(scenario_check)
    asyncio.run(scenario_check.main())
    assert "scenario_check ok" in capsys.readouterr().out
