import ast
import json
from enum import Enum
from typing import Annotated, Dict
from json.decoder import JSONDecodeError
import starlette.status as status
import yaml
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from database.models import (
    Interaction,
    Tech_Question,
    Behavior_Question,
    Personal_Question,
    Sessions,
)
from database.setup import db_dependency
from .auth import get_current_user
from .user import build_chat_model

router = APIRouter(tags=["answers"])

user_dependency = Annotated[dict, Depends(get_current_user)]


class QuestionType(str, Enum):
    tech = "techQ"
    behav = "behavQ"
    personal = "perQ"


class SingleAnswer(BaseModel):
    answer: str = Field(default="I DON'T KNOW")


class SingleResponse(BaseModel):
    type: QuestionType
    question: str
    user_answer: str
    evaluation: Dict


@router.get("/asked_question", status_code=status.HTTP_200_OK)
def asked_question(db: db_dependency, user: user_dependency) -> dict:
    tech_question_ids = get_asked_tech_question(db, user)
    behav_question_ids = get_asked_behav_question(db, user)
    personal_question_ids = get_asked_personal_question(db, user)
    return {
        "techQ_ids": tech_question_ids,
        "behavQ_ids": behav_question_ids,
        "perQ_ids": personal_question_ids,
    }


@router.post("/submit_tech_answer/{question_id}", status_code=status.HTTP_200_OK)
def submit_tech_answer(
    question_id: int, request: SingleAnswer, db: db_dependency, user: user_dependency
) -> SingleResponse:
    tech_question_ids = get_asked_tech_question(db, user)
    interaction_id = get_interaction_id(db, user)

    if question_id not in tech_question_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found in current session",
        )

    evaluation = evaluate_tech_answer(db, user, question_id, request.answer)

    # store_gpt_feedback(db, request.answer ,question_id, interaction_id, evaluation)

    tech_response = make_response(
        db, question_id, request, Tech_Question, QuestionType.tech, evaluation
    )

    store_user_answer(db, interaction_id, question_id, request.answer)
    return tech_response


@router.post("/submit_behav_answer/{question_id}", status_code=status.HTTP_200_OK)
def submit_behav_answer(
    question_id: int, request: SingleAnswer, db: db_dependency, user: user_dependency
) -> SingleResponse:
    behav_question_ids = get_asked_behav_question(db, user)
    interaction_id = get_interaction_id(db, user)

    if question_id not in behav_question_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found in current session",
        )
    # from gpt
    evaluation = evaluate_behav_answer(db, user, question_id, request.answer)

    behav_response = make_response(
        db,
        question_id,
        request,
        Behavior_Question,
        QuestionType.behav,
        evaluation,
    )
    store_user_answer(db, interaction_id, question_id, request.answer)
    return behav_response


@router.post("/submit_personal_answer/{question_id}", status_code=status.HTTP_200_OK)
def submit_personal_answer(
    question_id: int, request: SingleAnswer, db: db_dependency, user: user_dependency
) -> SingleResponse:

    evaluation = evaluate_personal_answer(
        db, user, question_id, request.answer
    )  # make with gpt
    personal_response = make_response(
        db,
        question_id,
        request,
        Personal_Question,
        QuestionType.personal,
        evaluation,
    )

    return personal_response


# Evaluate Tech answer
def evaluate_tech_answer(db, user, question_id, tech_answer):
    chat_model = build_chat_model(db, user)
    type = "techQ"
    question = (
        db.query(Tech_Question.question).filter(Tech_Question.id == question_id).first()
    )
    criteria = (
        db.query(Tech_Question.example_answer)
        .filter(Tech_Question.id == question_id)
        .first()
    )
    response, _ = chat_model.answer_evaluation(
        type=type, question=question, criteria=criteria, answer=tech_answer
    )
    print(response)
    return json_convert(response)


# Evaluate Behav answer
def evaluate_behav_answer(db, user, question_id, behav_answer):
    chat_model = build_chat_model(db, user)
    type = "behavQ"
    question = (
        db.query(Behavior_Question.question)
        .filter(Behavior_Question.id == question_id)
        .first()
    )
    criteria = (
        db.query(Behavior_Question.criteria)
        .filter(Behavior_Question.id == question_id)
        .first()
    )
    response, _ = chat_model.answer_evaluation(
        type=type, question=question, criteria=criteria, answer=behav_answer
    )
    print(response)

    return json_convert(response)


# Evaluate Personal answer
def evaluate_personal_answer(db, user, question_id, personal_answer):
    chat_model = build_chat_model(db, user)
    type = "perQ"

    question = (
        db.query(Personal_Question.question)
        .filter(Personal_Question.id == question_id)
        .first()
    )

    criteria = (
        db.query(Personal_Question.criteria)
        .filter(Personal_Question.id == question_id)
        .first()
    )

    response, _ = chat_model.answer_evaluation(
        type=type, question=question, criteria=criteria, answer=personal_answer
    )

    return json_convert(response)


def make_response(
    db, question_id, request, model, QuestionType, evaluation
) -> SingleResponse:
    question = db.query(model.question).filter(model.id == question_id).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    response = SingleResponse(
        type=QuestionType,
        question=question[0],
        user_answer=request.answer,
        evaluation=evaluation,
    )

    return response


def store_user_answer(db, interaction_id, question_id, user_answer) -> None:
    interaction_record = (
        db.query(Interaction).filter(Interaction.id == interaction_id).first()
    )
    if not interaction_record:
        raise HTTPException(status_code=404, detail="Interaction not found")

    current_answers = (
        json.loads(interaction_record.user_answers)
        if interaction_record.user_answers
        else []
    )
    current_answers.append({question_id: user_answer})
    interaction_record.user_answers = json.dumps(current_answers)

    db.commit()


# Store Qid, User answer, GPT Feedback
def store_gpt_feedback(db, user_answer, question_id, interaction_id, feedback) -> None:
    session_record = (
        db.query(Sessions).filter(Sessions.interaction_id == interaction_id).first()
    )
    if not session_record:
        raise HTTPException(status_code=404, detail="Session not found")

    current_feedback = (
        json.loads(session_record.feedback) if session_record.feedback else []
    )
    current_feedback.append(
        {"Qid": question_id, "user answer": user_answer, "feedback": feedback}
    )
    session_record.feedback = json.dumps(current_feedback)

    db.commit()


def get_asked_tech_question(db, user) -> list:
    interaction_id = get_interaction_id(db, user)
    tech_question_ids = (
        db.query(Interaction.tech_questions)
        .filter(Interaction.id == interaction_id)
        .first()[0]
    )
    return json.loads(tech_question_ids)


def get_asked_behav_question(db, user) -> list:
    interaction_id = get_interaction_id(db, user)
    behav_question_ids = (
        db.query(Interaction.behav_questions)
        .filter(Interaction.id == interaction_id)
        .first()[0]
    )
    return json.loads(behav_question_ids)


def get_asked_personal_question(db, user):
    session_id = get_session_id(db, user)
    personal_question_ids = (
        db.query(Personal_Question.id)
        .filter(Personal_Question.session_id == session_id)
        .all()
    )
    ids = [pq.id for pq in personal_question_ids]

    return ids


def get_session_id(db, user) -> int:
    session_id = (
        db.query(Sessions.id)
        .filter(Sessions.user_id == user.get("id"))
        .order_by(Sessions.id.desc())
        .first()[0]
    )
    return session_id


def get_interaction_id(db, user) -> int:
    interaction_id = (
        db.query(Sessions.interaction_id)
        .filter(Sessions.user_id == user.get("id"))
        .order_by(Sessions.id.desc())
        .first()[0]
    )
    return interaction_id


def json_convert(input_string):
    input_string = input_string.replace("'", '"')
    input_string = input_string.replace('"s ', "'s ")
    input_string = input_string.replace('"t ', "'t ")
    try:
        result = json.loads(input_string, strict=False)
        return result
    except JSONDecodeError as e:
        return {"error": f"JSON decode error: {str(e)}, Please Submit again"}
