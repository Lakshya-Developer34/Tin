"""Extract observations from interviews, cluster into themes, synthesize into digest."""

EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "observations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 50,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "interview_id": {"type": "integer"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "pain_point",
                            "need",
                            "feature_request",
                            "positive_feedback",
                            "surprise",
                            "quote",
                        ],
                    },
                    "text": {"type": "string", "minLength": 10, "maxLength": 500},
                    "significance": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["interview_id", "category", "text", "significance"],
            },
        }
    },
    "required": ["observations"],
}

SYNTHESIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "themes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 5, "maxLength": 100},
                    "insight": {"type": "string", "minLength": 20, "maxLength": 300},
                    "participant_count": {"type": "integer", "minimum": 2},
                    "observation_count": {"type": "integer", "minimum": 2},
                    "quotes": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {"type": "string", "minLength": 10, "maxLength": 400},
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": [
                    "name",
                    "insight",
                    "participant_count",
                    "observation_count",
                    "quotes",
                    "confidence",
                ],
            },
        },
        "pain_points": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string", "minLength": 10, "maxLength": 200},
                    "frequency": {"type": "integer", "minimum": 1},
                    "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["description", "frequency", "impact"],
            },
        },
        "unmet_needs": {
            "type": "array",
            "minItems": 0,
            "maxItems": 5,
            "items": {"type": "string", "minLength": 10, "maxLength": 200},
        },
        "recommendations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string", "minLength": 10, "maxLength": 200},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "evidence": {"type": "string", "minLength": 10, "maxLength": 200},
                },
                "required": ["action", "priority", "evidence"],
            },
        },
    },
    "required": ["themes", "pain_points", "unmet_needs", "recommendations"],
}


async def run(ctx, inputs):
    """Extract, cluster, and synthesize interview observations."""
    interviews = inputs["interviews"]
    research_objective = inputs["research_objective"]
    participant_context = inputs.get("participant_context", "")

    # Assign IDs to interviews
    interview_items = [{"id": index, "text": text} for index, text in enumerate(interviews)]

    # Step 1: Extract observations
    extraction = await ctx.models.generate(
        route="extract",
        step="extract_observations",
        instructions=(
            "Extract atomic observations from each interview. "
            "Categories: pain_point (frustration/problem), need (what they want), "
            "feature_request (specific feature ask), positive_feedback (what works), "
            "surprise (unexpected), quote (verbatim). "
            "Preserve each interview_id exactly. Mark significance based on impact."
        ),
        data=interview_items,
        output_schema=EXTRACTION_SCHEMA,
    )

    observations = extraction["parsed"]["observations"]

    # Validate interview IDs are preserved
    extracted_ids = {obs["interview_id"] for obs in observations}
    expected_ids = set(range(len(interviews)))
    if not extracted_ids.issubset(expected_ids):
        raise ValueError("Extraction must preserve valid interview IDs")

    # Cluster observations by category and count frequency
    from collections import defaultdict

    by_category = defaultdict(list)
    for obs in observations:
        by_category[obs["category"]].append(obs)

    # Build frequency map per interview
    interview_observations = defaultdict(list)
    for obs in observations:
        interview_observations[obs["interview_id"]].append(obs)

    # Prepare clustered data for synthesis
    clustered = {
        "total_interviews": len(interviews),
        "total_observations": len(observations),
        "by_category": {cat: len(obs_list) for cat, obs_list in by_category.items()},
        "observations_by_interview": {
            iid: len(obs_list) for iid, obs_list in interview_observations.items()
        },
        "observations": observations,
    }

    # Step 2: Synthesize themes and recommendations
    synthesis = await ctx.models.generate(
        route="synthesize",
        step="synthesize_themes",
        instructions=(
            "Synthesize the clustered observations into themes, insights, and recommendations. "
            "Themes must appear in 2+ interviews. Extract verbatim quotes from the "
            "original observations. "
            "Prioritize recommendations by impact and evidence strength. "
            "Be honest about limitations in the confidence field."
        ),
        data={
            "research_objective": research_objective,
            "participant_context": participant_context,
            "clustered": clustered,
        },
        output_schema=SYNTHESIS_SCHEMA,
    )

    result = synthesis["parsed"]

    # Render markdown report
    lines = [
        "# Interview Digest",
        "",
        f"**Research objective:** {research_objective}",
        f"**Interviews:** {len(interviews)}",
        f"**Observations extracted:** {len(observations)}",
    ]

    if participant_context:
        lines.append(f"**Participant context:** {participant_context}")

    lines.extend(["", "---", "", "## Key Themes", ""])

    for theme in result["themes"]:
        lines.append(f"### {theme['name']}")
        lines.append(f"**Insight:** {theme['insight']}")
        lines.append(
            f"**Mentioned by:** {theme['participant_count']}/{len(interviews)} participants"
        )
        lines.append(f"**Confidence:** {theme['confidence']}")
        lines.append("")
        lines.append("**Supporting quotes:**")
        for quote in theme["quotes"]:
            lines.append(f"> {quote}")
        lines.append("")

    lines.extend(["---", "", "## Pain Points", ""])
    for pain in result["pain_points"]:
        lines.append(
            f"- **{pain['description']}** (mentioned by {pain['frequency']}, "
            f"impact: {pain['impact']})"
        )

    lines.extend(["", "---", "", "## Unmet Needs", ""])
    if result["unmet_needs"]:
        for need in result["unmet_needs"]:
            lines.append(f"- {need}")
    else:
        lines.append("No explicit unmet needs identified.")

    lines.extend(["", "---", "", "## Recommendations", ""])
    for rec in result["recommendations"]:
        lines.append(f"### [{rec['priority'].upper()}] {rec['action']}")
        lines.append(f"**Evidence:** {rec['evidence']}")
        lines.append("")

    lines.extend(["---", "", "## Limitations", ""])
    lines.append(f"- Sample size: {len(interviews)} interviews")
    lines.append("- Findings reflect stated preferences, not observed behavior")
    lines.append("- Confidence levels based on frequency and clarity of evidence")

    content = "\n".join(lines)

    return {"path": "research/INTERVIEW_DIGEST.md", "content": content}
