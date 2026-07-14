"""ReAct AgentExecutor qurulması.

ReAct nümunəsi: agent "Thought -> Action -> Observation" dövrü ilə
düşünür, alət çağırır, nəticəni görür və yekun cavaba gəlir.
Format açar sözləri (Action, Final Answer) LangChain parser-inin
tələbi ilə ingiliscə saxlanılır, təlimatlar isə Azərbaycancadır.
"""
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from app.agent.llm_adapter import ProviderLLM
from app.agent.tools import build_tools
from app.config import get_settings
from app.prompts import AGENT_SYSTEM
from app.providers.llm.base import BaseLLMProvider

# Klassik ReAct şablonu (hwchase17/react əsasında, Azərbaycan dilinə uyğunlaşdırılıb)
REACT_TEMPLATE = """{system}

Sənin istifadə edə biləcəyin alətlər:

{tools}

DƏQİQ bu formatdan istifadə et:

Question: cavablandırılmalı sual
Thought: nə etməli olduğunu düşün
Action: bu alətlərdən biri: [{tool_names}]
Action Input: alətə göndərilən mətn
Observation: alətin nəticəsi
... (Thought/Action/Action Input/Observation bir neçə dəfə təkrarlana bilər)
Thought: İndi yekun cavabı bilirəm
Final Answer: istifadəçinin iclasda deyə biləcəyi cavab qaralaması

Begin!

Question: {input}
Thought:{agent_scratchpad}"""


def build_agent_executor(meeting_id: str, llm_provider: BaseLLMProvider) -> AgentExecutor:
    """Verilən iclas üçün ReAct AgentExecutor yaradır."""
    settings = get_settings()
    llm = ProviderLLM(provider=llm_provider)
    tools = build_tools(meeting_id)

    prompt = PromptTemplate.from_template(REACT_TEMPLATE).partial(system=AGENT_SYSTEM)
    agent = create_react_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=settings.agent_max_iterations,  # sonsuz dövrdən qoruyur
        handle_parsing_errors=True,                    # format pozulsa dayanmasın
        return_intermediate_steps=True,                # addımları feed-də göstəririk
        verbose=False,
    )
