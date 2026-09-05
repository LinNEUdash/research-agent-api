"""
Task definitions for the Research Assistant workflow.

Sequential pipeline:
  1. research_task   — Researcher gathers raw information
  2. analysis_task   — Analyst evaluates and summarizes
  3. report_task     — Controller synthesizes final report
"""

from crewai import Task, Agent


def create_research_task(researcher: Agent, query: str) -> Task:
    """Task 1: Gather information from the web."""
    return Task(
        description=(
            f"Research the following topic thoroughly:\n\n"
            f"'{query}'\n\n"
            f"Instructions:\n"
            f"1. Perform at least 3 different web searches with varied queries.\n"
            f"2. For each relevant result, record: title, URL, publication date "
            f"   (if available), and a 2-3 sentence summary of key findings.\n"
            f"3. Scrape at least 2 of the most promising pages for detailed content.\n"
            f"4. Prioritize recent sources (within the last 2 years).\n"
            f"5. Include sources from different perspectives when applicable.\n"
            f"6. Note whether each source has a named author and citations."
        ),
        expected_output=(
            "A structured collection of research findings with:\n"
            "- At least 5 relevant sources\n"
            "- For each source: title, URL, date, author (if known), "
            "whether it has citations, and key findings summary\n"
            "- A brief note on any gaps in the available information"
        ),
        agent=researcher,
    )


def create_analysis_task(analyst: Agent, research_task: Task) -> Task:
    """Task 2: Evaluate sources and synthesize findings."""
    return Task(
        description=(
            "Analyze the research findings from the previous task:\n\n"
            "1. Use the Source Credibility Scorer tool to evaluate EACH source URL.\n"
            "   Pass the URL, publication_date, has_author, and has_citations.\n"
            "2. Identify the top 3-5 most credible sources.\n"
            "3. Extract and organize key themes across sources.\n"
            "4. Flag any contradictions between sources.\n"
            "5. Note claims that appear in only one source (unverified).\n"
            "6. Summarize the consensus view and minority opinions."
        ),
        expected_output=(
            "A structured analysis containing:\n"
            "- Credibility scores for each source (from the Credibility Scorer)\n"
            "- Ranked list of sources by credibility\n"
            "- Key themes with supporting evidence\n"
            "- Contradictions and unverified claims flagged\n"
            "- Confidence level for each major finding (high/medium/low)"
        ),
        agent=analyst,
        context=[research_task],
    )


def create_report_task(controller: Agent, analysis_task: Task, query: str) -> Task:
    """Task 3: Synthesize everything into a final research report."""
    return Task(
        description=(
            f"Produce the final research report for the query:\n\n"
            f"'{query}'\n\n"
            f"Using the analyst's evaluation, write a comprehensive report with:\n"
            f"1. Executive Summary (3-5 sentences)\n"
            f"2. Key Findings (organized by theme, each with confidence level)\n"
            f"3. Source Analysis (credibility rankings, best/worst sources)\n"
            f"4. Contradictions & Open Questions\n"
            f"5. Conclusion & Recommendations for further research\n"
            f"6. References (list all sources with credibility scores)\n\n"
            f"The report should be clear, balanced, and actionable. "
            f"Avoid unsupported claims."
        ),
        expected_output=(
            "A polished research report in Markdown format with all 6 sections. "
            "Each finding should cite its source. The report should be "
            "2000-3000 words and suitable for an informed reader."
        ),
        agent=controller,
        context=[analysis_task],
    )
