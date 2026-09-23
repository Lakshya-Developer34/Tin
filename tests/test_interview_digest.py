"""Offline checks for interview digest workflow."""

import json
import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]


def example_interview_digest():
    """Load the interview digest package for testing."""
    root = REPOSITORY_ROOT / "workflow_packages" / "research.interview_digest"
    definition = json.loads((root / "workflow.json").read_text())["definition"]
    module = SimpleNamespace(**runpy.run_path(str(root / "main.py")))
    return module, definition


@pytest.mark.parametrize("invalid_ids", [False, True])
async def test_two_model_steps_extract_then_synthesize(invalid_ids):
    """Test that extraction preserves IDs and synthesis uses clustered data."""
    module, definition = example_interview_digest()
    calls = []

    async def generate(**payload):
        calls.append(payload)

        if payload["step"] == "extract_observations":
            if invalid_ids:
                output = {
                    "observations": [
                        {
                            "interview_id": 99,
                            "category": "pain_point",
                            "text": "Slow loading",
                            "significance": "high",
                        }
                    ]
                }
            else:
                output = {
                    "observations": [
                        {
                            "interview_id": 0,
                            "category": "pain_point",
                            "text": "Slow loading",
                            "significance": "high",
                        },
                        {
                            "interview_id": 1,
                            "category": "need",
                            "text": "Better export",
                            "significance": "medium",
                        },
                        {
                            "interview_id": 2,
                            "category": "quote",
                            "text": "I love the UI",
                            "significance": "low",
                        },
                    ]
                }
        else:
            # Synthesize step
            assert payload["data"]["clustered"]["total_interviews"] == 3
            output = {
                "themes": [
                    {
                        "name": "Performance issues",
                        "insight": "Users experience frustration with slow load times affecting productivity",
                        "participant_count": 2,
                        "observation_count": 2,
                        "quotes": ["Slow loading", "It takes forever to load"],
                        "confidence": "high",
                    }
                ],
                "pain_points": [
                    {"description": "Slow page load times", "frequency": 2, "impact": "high"}
                ],
                "unmet_needs": ["Better export functionality"],
                "recommendations": [
                    {
                        "action": "Optimize page load performance",
                        "priority": "high",
                        "evidence": "2 participants mentioned slow loading",
                    }
                ],
            }

        return {"parsed": output, "text": json.dumps(output)}

    context = SimpleNamespace(models=SimpleNamespace(generate=generate), run_id=str(uuid4()))

    inputs = {
        "interviews": [
            "Interview 1: User complained about slow loading times",
            "Interview 2: User needs better export feature",
            "Interview 3: User loves the UI but wants faster performance",
        ],
        "research_objective": "Understand user pain points",
        "participant_context": "All users are enterprise customers",
    }

    if invalid_ids:
        with pytest.raises(ValueError, match="preserve valid interview IDs"):
            await module.run(context, inputs)
        assert len(calls) == 1
    else:
        result = await module.run(context, inputs)
        assert [c["step"] for c in calls] == ["extract_observations", "synthesize_themes"]
        assert "Key Themes" in result["content"]
        assert "Performance issues" in result["content"]
        assert "Recommendations" in result["content"]
