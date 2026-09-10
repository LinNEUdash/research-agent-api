"""
Agent definitions for the Research Assistant system.

Three agents with distinct roles:
  1. Controller  — decomposes queries, delegates, synthesizes final report
  2. Researcher  — searches the web and scrapes relevant pages
  3. Analyst     — summarizes findings and scores source credibility
"""

from typing import Union

from crewai import LLM, Agent
from crewai_tools import SerperDevTool, FileReadTool

from tools.bounded_scraper import BoundedScrapeWebsiteTool
from tools.credibility_scorer import SourceCredibilityScorer

# Only a fallback; crew_runner passes a configured LLM. gemini-2.0-flash used
# to sit here and was retired by the provider, so a caller relying on the
# default got a 404 rather than a working agent.
DEFAULT_MODEL = "gemini/gemini-2.5-flash"


def create_controller_agent(model: Union[str, LLM] = DEFAULT_MODEL) -> Agent:
    """Controller agent — orchestrates the research workflow."""
    return Agent(
        role="Research Controller",
        goal=(
            "Break down the user's research question into actionable sub-tasks, "
            "delegate them to the Research Agent and Analyst Agent, and synthesize "
            "their outputs into a coherent, well-structured research report."
        ),
        backstory=(
            "You are a senior research manager with 15 years of experience leading "
            "academic and industry research teams. You excel at identifying the key "
            "dimensions of a research question, prioritizing what information to "
            "gather first, and spotting gaps in collected evidence. You insist on "
            "source quality and always cross-reference findings before including "
            "them in a final report."
        ),
        verbose=True,
        memory=True,
        allow_delegation=True,
        llm=model,
    )


def create_researcher_agent(model: Union[str, LLM] = DEFAULT_MODEL) -> Agent:
    """Research agent — gathers information from the web."""
    return Agent(
        role="Web Researcher",
        goal=(
            "Find the most relevant, authoritative, and recent information on "
            "the assigned research sub-topics using web search and scraping. "
            "Return raw findings with source URLs and publication dates."
        ),
        backstory=(
            "You are an expert research analyst skilled at crafting precise "
            "search queries and quickly identifying high-quality sources. You "
            "know how to distinguish primary sources from secondary commentary "
            "and always record the URL and date for every piece of information."
        ),
        verbose=True,
        memory=True,
        allow_delegation=False,
        tools=[
            SerperDevTool(),
            BoundedScrapeWebsiteTool(),
        ],
        llm=model,
    )


def create_analyst_agent(model: Union[str, LLM] = DEFAULT_MODEL) -> Agent:
    """Analyst agent — evaluates, summarizes, and fact-checks findings."""
    return Agent(
        role="Research Analyst",
        goal=(
            "Analyze the raw research findings, evaluate source credibility, "
            "identify key themes and contradictions, and produce a structured "
            "analysis with credibility scores for each source."
        ),
        backstory=(
            "You are a critical-thinking analyst with expertise in information "
            "verification and academic writing. You are trained to detect bias, "
            "evaluate evidence quality, and synthesize multiple perspectives into "
            "balanced, nuanced summaries. You always flag uncertain claims and "
            "rate every source's trustworthiness."
        ),
        verbose=True,
        memory=True,
        allow_delegation=False,
        tools=[
            FileReadTool(),
            SourceCredibilityScorer(),
        ],
        llm=model,
    )
