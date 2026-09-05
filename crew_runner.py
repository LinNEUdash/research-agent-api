"""Runs the CrewAI research crew and returns the finished report.

This is the original pipeline from the CLI version, with the command-line
handling and file writing stripped out so it can be called from a web request.
"""

import logging

from crewai import Crew, Process

from agents import (
    create_analyst_agent,
    create_controller_agent,
    create_researcher_agent,
)
from config.settings import LLM_MODEL
from tasks import (
    create_analysis_task,
    create_report_task,
    create_research_task,
)

logger = logging.getLogger(__name__)

# The crew makes many model and tool calls per run. Capping requests per minute
# keeps us inside third-party quotas and makes the cost of a single run
# predictable.
MAX_REQUESTS_PER_MINUTE = 10


def build_crew(query: str) -> Crew:
    """Assemble the three-stage research crew for a single query."""
    controller = create_controller_agent(model=LLM_MODEL)
    researcher = create_researcher_agent(model=LLM_MODEL)
    analyst = create_analyst_agent(model=LLM_MODEL)

    # Each task takes the previous one as context, which is how output flows
    # from stage to stage. Crew-level memory is off; the context chain is the
    # only state that crosses task boundaries.
    research_task = create_research_task(researcher, query)
    analysis_task = create_analysis_task(analyst, research_task)
    report_task = create_report_task(controller, analysis_task, query)

    return Crew(
        agents=[controller, researcher, analyst],
        tasks=[research_task, analysis_task, report_task],
        process=Process.sequential,
        verbose=True,
        memory=False,
        max_rpm=MAX_REQUESTS_PER_MINUTE,
    )


def run_research(query: str) -> str:
    """Run the crew end to end and return the report as markdown."""
    logger.info("crew starting", extra={"query": query})
    crew = build_crew(query)
    report = str(crew.kickoff())
    logger.info("crew finished", extra={"query": query, "chars": len(report)})
    return report
