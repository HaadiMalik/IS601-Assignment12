import uuid
from datetime import datetime, timezone, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User


client = TestClient(app)


def make_mock_db_for_query(return_value):
    mock_db = mock.Mock()
    mock_query = mock.Mock()
    mock_query.filter.return_value = mock.Mock()
    # allow chaining .filter(...).first() and .all()
    mock_query.filter.return_value.first.return_value = return_value
    mock_query.filter.return_value.all.return_value = return_value if isinstance(return_value, list) else [return_value]
    mock_db.query.return_value = mock_query
    return mock_db


def test_register_value_error_returns_400(mock_db_session):
    # Pydantic validation must pass; patch User.register to raise ValueError
    user_create_data = {
        "username": "testuser2",
        "email": "test2@example.com",
        "password": "TestPass123!",
        "confirm_password": "TestPass123!",
        "first_name": "Test",
        "last_name": "User"
    }

    with mock.patch.object(User, "register", side_effect=ValueError("Something went wrong")):
        # Ensure get_db returns a mocked session
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.post("/auth/register", json=user_create_data)

    assert response.status_code == 400
    assert response.json()["detail"] == "Something went wrong"


def test_login_json_failure(mock_db_session):
    with mock.patch.object(User, "authenticate", return_value=None):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.post("/auth/login", json={"username": "u", "password": "p"})
    assert response.status_code == 401


def test_login_json_success_with_naive_datetime(mock_db_session):
    # Setup a user-like object
    mock_user = mock.Mock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.username = "u1"
    mock_user.email = "e@example.com"
    mock_user.first_name = "F"
    mock_user.last_name = "L"
    mock_user.is_active = True
    mock_user.is_verified = False

    naive_expires = datetime.now()  # tzinfo is None

    auth_result = {
        "access_token": "a",
        "refresh_token": "r",
        "user": mock_user,
        "expires_at": naive_expires
    }

    with mock.patch.object(User, "authenticate", return_value=auth_result):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.post("/auth/login", json={"username": "u1", "password": "p"})

    assert response.status_code == 200
    body = response.json()
    assert "expires_at" in body


def test_login_json_success_when_expires_missing(mock_db_session):
    # When authenticate returns no expires_at, the code sets a default ~15 minutes out
    mock_user = mock.Mock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.username = "u1"
    mock_user.email = "e@example.com"
    mock_user.first_name = "F"
    mock_user.last_name = "L"
    mock_user.is_active = True
    mock_user.is_verified = False

    auth_result = {"access_token": "a", "refresh_token": "r", "user": mock_user}

    with mock.patch.object(User, "authenticate", return_value=auth_result):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.post("/auth/login", json={"username": "u1", "password": "p"})

    assert response.status_code == 200
    body = response.json()
    # expires_at should be roughly ~15 minutes from now
    from datetime import datetime as dt
    expires = dt.fromisoformat(body["expires_at"])
    assert expires > datetime.now(timezone.utc)


def test_login_form_failure(mock_db_session):
    with mock.patch.object(User, "authenticate", return_value=None):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.post("/auth/token", data={"username": "u", "password": "p"})
    assert response.status_code == 401


def test_login_form_success(mock_db_session):
    auth_result = {"access_token": "a", "refresh_token": "r", "user": mock.Mock(spec=User)}
    with mock.patch.object(User, "authenticate", return_value=auth_result):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.post("/auth/token", data={"username": "u", "password": "p"})

    assert response.status_code == 200
    assert response.json()["access_token"] == "a"


def test_create_calculation_value_error(mock_db_session):
    # Patch current user dependency to provide an object with an id
    mock_user = mock.Mock()
    mock_user.id = uuid.uuid4()

    with mock.patch("app.main.get_current_active_user", return_value=mock_user):
        # Make Calculation.create raise ValueError
        with mock.patch("app.main.Calculation.create", side_effect=ValueError("Bad inputs")):
            with mock.patch("app.main.get_db", return_value=mock_db_session):
                response = client.post(
                    "/calculations",
                    json={"type": "addition", "inputs": [1, 2, 3]}
                )

    assert response.status_code == 400
    assert response.json()["detail"] == "Bad inputs"


def test_get_calculation_invalid_uuid(mock_db_session):
    with mock.patch("app.main.get_current_active_user", return_value=mock.Mock()):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.get("/calculations/not-a-uuid")
    assert response.status_code == 400


def test_get_calculation_not_found(mock_db_session):
    mock_db = make_mock_db_for_query(None)
    with mock.patch("app.main.get_current_active_user", return_value=mock.Mock()):
        with mock.patch("app.main.get_db", return_value=mock_db):
            response = client.get(f"/calculations/{uuid.uuid4()}")
    assert response.status_code == 404


def test_update_calculation_invalid_uuid(mock_db_session):
    with mock.patch("app.main.get_current_active_user", return_value=mock.Mock()):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.put("/calculations/not-a-uuid", json={"inputs": [1,2]})
    assert response.status_code == 400


def test_update_calculation_not_found(mock_db_session):
    mock_db = make_mock_db_for_query(None)
    with mock.patch("app.main.get_current_active_user", return_value=mock.Mock()):
        with mock.patch("app.main.get_db", return_value=mock_db):
            response = client.put(f"/calculations/{uuid.uuid4()}", json={"inputs": [1,2]})
    assert response.status_code == 404


def test_delete_calculation_invalid_uuid(mock_db_session):
    with mock.patch("app.main.get_current_active_user", return_value=mock.Mock()):
        with mock.patch("app.main.get_db", return_value=mock_db_session):
            response = client.delete("/calculations/not-a-uuid")
    assert response.status_code == 400


def test_delete_calculation_not_found(mock_db_session):
    mock_db = make_mock_db_for_query(None)
    with mock.patch("app.main.get_current_active_user", return_value=mock.Mock()):
        with mock.patch("app.main.get_db", return_value=mock_db):
            response = client.delete(f"/calculations/{uuid.uuid4()}")
    assert response.status_code == 404
