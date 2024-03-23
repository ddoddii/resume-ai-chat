from sqlalchemy import text
from sqlalchemy import create_engine
import csv
import os
from dotenv import load_dotenv

load_dotenv()

# CSV PATH and TABLE NAME
# ========================= #
CSV_PATH = "./input/questions/behav_q.csv"
TABLE_NAME = "behavior_question"
# ========================= #

SQLALCEMY_DATABASE_URL = os.getenv("SQLALCEMY_DATABASE_URL")

engine = create_engine(
    SQLALCEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


def insert_data(db, table, rows):
    for row in rows:
        db.execute(
            text(
                f"INSERT INTO {table} (questions, criteria ) VALUES (:questions, :criteria)"
            ),
            row,
        )
    db.commit()


def csv_to_database(CSV_PATH, TABLE_NAME):
    with open(CSV_PATH, "r", encoding="utf-8-sig") as file:
        csv_reader = csv.DictReader(file)
        data = [row for row in csv_reader]

    with engine.connect() as connection:
        insert_data(connection, TABLE_NAME, data)


if __name__ == "__main__":
    csv_to_database(CSV_PATH, TABLE_NAME)
    print("database update done!")
