# db_logger.py
# ============================================================
# Smart Atlas — Database Activity Logger
# Uses YOUR existing tables:
#   login_history  — login events
#   travel_costs   — destination searches
#   users          — update last_login on each login
# ============================================================

import logging
import datetime

logger = logging.getLogger(__name__)


def log_login(conn, user: dict) -> bool:
    """
    Record a successful login into login_history
    AND update users.last_login timestamp.

    login_history columns:
        user_id, email, login_time, ip_address, success
    """
    if not conn or not user:
        return False
    try:
        cur = conn.cursor()

        # 1. Insert into login_history
        cur.execute(
            """INSERT INTO login_history
               (user_id, email, login_time, ip_address, success)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                user.get("id", 0),
                user.get("email", ""),
                datetime.datetime.now(),
                "streamlit-local",
                1,
            ),
        )

        # 2. Update last_login in users table
        cur.execute(
            "UPDATE users SET last_login = %s WHERE id = %s",
            (datetime.datetime.now(), user.get("id", 0)),
        )

        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error("db_logger: log_login failed: %s", e)
        return False


def log_search(conn, user: dict, destination: str, search_type: str = "home") -> bool:
    """
    Record a destination search into travel_costs.
    Uses cost=0.00 and travel_date=today as placeholders
    since the actual cost is calculated later in the dashboard.

    travel_costs columns:
        user_id, destination, cost, travel_date, created_at
    """
    if not conn or not user or not destination:
        return False
    destination = destination.strip().title()
    if not destination:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO travel_costs
               (user_id, destination, cost, travel_date)
               VALUES (%s, %s, %s, %s)""",
            (
                user.get("id", 0),
                destination,
                0.00,
                datetime.date.today(),
            ),
        )
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error("db_logger: log_search failed: %s", e)
        return False


def get_user_search_history(conn, user_id: int, limit: int = 20) -> list:
    """
    Fetch a user's recent destination searches from travel_costs.
    Returns list of dicts: {destination, travel_date, created_at}
    """
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT destination, travel_date, created_at
               FROM travel_costs
               WHERE user_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (user_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        logger.error("db_logger: get_user_search_history failed: %s", e)
        return []


def get_top_destinations(conn, limit: int = 10) -> list:
    """
    Most searched destinations across all users.
    Returns list of dicts: {destination, count}
    """
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT destination, COUNT(*) AS count
               FROM travel_costs
               GROUP BY destination
               ORDER BY count DESC
               LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        logger.error("db_logger: get_top_destinations failed: %s", e)
        return []


def get_login_history(conn, user_id: int, limit: int = 10) -> list:
    """
    Fetch recent login records for a user from login_history.
    Returns list of dicts: {email, login_time, ip_address, success}
    """
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT email, login_time, ip_address, success
               FROM login_history
               WHERE user_id = %s
               ORDER BY login_time DESC
               LIMIT %s""",
            (user_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        logger.error("db_logger: get_login_history failed: %s", e)
        return []
