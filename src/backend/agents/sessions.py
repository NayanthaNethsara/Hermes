import asyncio
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import delete, desc, select

from src.backend.agents.llm import get_chat_model
from src.backend.core.database import ChatSessionModel, session_scope
from src.backend.core.exceptions import summarize_error
from src.backend.core.logging import get_logger
from src.backend.core.redis import redis_delete, redis_get_json, redis_set_json

logger = get_logger("sessions")


async def generate_concise_title(session_id: str, first_question: str) -> None:
    try:
        llm = get_chat_model(temperature=0.0)
        prompt = (
            f"Question: {first_question}\n\n"
            "Generate a 3 to 4 word topic title for this historical archive investigation (no quotes, no period, Title Case):"
        )
        response = await llm.ainvoke([
            SystemMessage(content="You are a concise headline writer for historical archive research."),
            HumanMessage(content=prompt),
        ])
        raw_title = response.content if isinstance(response.content, str) else str(response.content)
        title = raw_title.strip().strip('"').strip("'").strip()
        if not title:
            return

        async with session_scope() as session:
            query = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
            result = await session.execute(query)
            record = result.scalar_one_or_none()
            if record:
                record.title = title
                logger.info("session_title_updated", session_id=session_id, title=title)
                await redis_delete("cache:sessions:list")
    except Exception as error:
        logger.warning("session_title_generation_failed", error=summarize_error(error))


async def update_session_summary_in_background(session_id: str, turns: list[dict[str, Any]]) -> None:
    if len(turns) < 3:
        return
    try:
        from src.backend.agents.graphs.workflow import get_compiled_graph

        turn_texts: list[str] = []
        for index, turn in enumerate(turns[-4:], start=1):
            question_text = turn.get("question", "")
            answer_text = turn.get("response", {}).get("answer", "")[:250]
            turn_texts.append(f"Turn {index}:\nUser: {question_text}\nArchive: {answer_text}")

        history_block = "\n\n".join(turn_texts)
        llm = get_chat_model(temperature=0.0)
        summary_prompt = (
            "Summarize the key facts, named entities, and topics established in these recent dialogue turns "
            "into a concise 2 to 3 sentence rolling summary for query disambiguation:\n\n"
            f"{history_block}"
        )
        response = await llm.ainvoke([
            SystemMessage(content="You are a concise research note keeper for archive investigations."),
            HumanMessage(content=summary_prompt),
        ])
        raw_summary = response.content if isinstance(response.content, str) else str(response.content)
        summary = raw_summary.strip()
        if not summary:
            return

        async with session_scope() as session:
            query = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
            result = await session.execute(query)
            record = result.scalar_one_or_none()
            if record:
                record.summary = summary

        graph = await get_compiled_graph()
        config = {"configurable": {"thread_id": session_id}}
        await graph.aupdate_state(config, {"session_summary": summary})
        logger.info("session_summary_updated", session_id=session_id)
    except Exception as error:
        logger.warning("session_summary_update_failed", error=summarize_error(error))


async def upsert_session(
    session_id: str,
    question: str,
    response_payload: dict[str, Any],
) -> None:
    """Persist one turn. Never raises: an answer already produced for the
    caller must not be lost to a database or cache outage."""
    try:
        await persist_session_turn(session_id, question, response_payload)
    except Exception as error:
        logger.warning(
            "session_history_persist_failed",
            session_id=session_id,
            error=summarize_error(error),
        )


async def persist_session_turn(
    session_id: str,
    question: str,
    response_payload: dict[str, Any],
) -> None:
    if not session_id or session_id == "default":
        return

    new_turn = {
        "question": question,
        "response": response_payload,
    }

    clean_title = question.strip()
    if len(clean_title) > 60:
        clean_title = clean_title[:57] + "..."

    async with session_scope() as session:
        query = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
        result = await session.execute(query)
        record = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record is None:
            new_record = ChatSessionModel(
                id=session_id,
                title=clean_title or "Untitled Investigation",
                created_at=now,
                updated_at=now,
                turns_json=[new_turn],
            )
            session.add(new_record)
            asyncio.create_task(generate_concise_title(session_id, question))
        else:
            current_turns = list(record.turns_json or [])
            current_turns.append(new_turn)
            record.turns_json = current_turns
            record.updated_at = now
            if len(current_turns) >= 3 and len(current_turns) % 2 == 1:
                asyncio.create_task(update_session_summary_in_background(session_id, current_turns))

        await redis_delete("cache:sessions:list")
        logger.info("session_history_persisted", session_id=session_id)


async def list_sessions() -> list[dict[str, Any]]:
    cached_sessions = await redis_get_json("cache:sessions:list")
    if cached_sessions is not None and isinstance(cached_sessions, list):
        return cached_sessions

    async with session_scope() as session:
        query = select(ChatSessionModel).order_by(desc(ChatSessionModel.updated_at))
        result = await session.execute(query)
        records = result.scalars().all()

        sessions_payload = [
            {
                "id": record.id,
                "title": record.title,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "turn_count": len(record.turns_json or []),
            }
            for record in records
        ]
        await redis_set_json("cache:sessions:list", sessions_payload, ttl_seconds=60)
        return sessions_payload


async def get_session(session_id: str) -> dict[str, Any] | None:
    async with session_scope() as session:
        query = select(ChatSessionModel).where(ChatSessionModel.id == session_id)
        result = await session.execute(query)
        record = result.scalar_one_or_none()

        if record is None:
            return None

        return {
            "id": record.id,
            "title": record.title,
            "summary": record.summary,
            "turns": record.turns_json or [],
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }


async def delete_session(session_id: str) -> bool:
    async with session_scope() as session:
        query = delete(ChatSessionModel).where(ChatSessionModel.id == session_id)
        result = await session.execute(query)
        is_deleted = (result.rowcount or 0) > 0
        if is_deleted:
            await redis_delete("cache:sessions:list")
            logger.info("session_deleted", session_id=session_id)
        return is_deleted
