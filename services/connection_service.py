from datetime import datetime
from services.token_encryption import encrypt_token, decrypt_token
from firebase import db


def create_connection(
    business_id,
    user_id,
    provider,
    connection_data,
):

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        raise PermissionError(
            "You do not have permission to modify this business"
        )

    now = datetime.utcnow().isoformat()

    if "access_token" in connection_data:
        connection_data = {
            **connection_data,
            "access_token": encrypt_token(
                connection_data["access_token"]
            ),
        }

    connection = {
        "provider": provider,
        "status": "connected",
        "created_at": now,
        "updated_at": now,
        **connection_data,
    }

    connection_ref = (
        business_ref
        .collection("connections")
        .document()
    )

    connection_ref.set(connection)

    return {
        "id": connection_ref.id,
        **connection,
    }
    



def get_connection(
    business_id,
    user_id,
    provider,
):
    """
    Retrieve a connected external platform account.

    The access token is decrypted internally and returned
    only to backend code that explicitly needs it.
    """

    business_ref = (
        db.collection("businesses")
        .document(business_id)
    )

    business_doc = business_ref.get()

    if not business_doc.exists:
        raise ValueError("Business not found")

    business = business_doc.to_dict()

    if business.get("owner_id") != user_id:
        raise PermissionError(
            "You do not have permission to access this business"
        )

    connections = (
        business_ref
        .collection("connections")
        .where(
            "provider",
            "==",
            provider,
        )
        .where(
            "status",
            "==",
            "connected",
        )
        .order_by(
            "updated_at",
            direction="DESCENDING",
        )
        .limit(1)
        .stream()
    )

    connection_doc = next(
        connections,
        None,
    )

    if not connection_doc:
        raise ValueError(
            f"No connected {provider} account found"
        )

    connection = connection_doc.to_dict()

    encrypted_token = connection.get(
        "access_token"
    )

    if not encrypted_token:
        raise ValueError(
            "Connection does not contain an access token"
        )

    access_token = decrypt_token(
        encrypted_token
    )

    return {
        "id": connection_doc.id,
        "provider": connection.get(
            "provider"
        ),
        "account_id": connection.get(
            "account_id"
        ),
        "username": connection.get(
            "username"
        ),
        "site_id": connection.get(
            "site_id"
        ),
        "token_expires_at": connection.get(
            "token_expires_at"
        ),
        "repository": connection.get(
            "repository"
        ),
        "default_branch": connection.get(
            "default_branch"
        ),
        "access_token": access_token,
    }
    
def create_github_connection(
    business_id,
    user_id,
    access_token,
    owner,
    repo,
    default_branch=None,
):
    connection_data = {
        "account_id": owner,
        "repository": repo,
    }

    if default_branch:
        connection_data["default_branch"] = default_branch

    return create_connection(
        business_id=business_id,
        user_id=user_id,
        provider="github",
        connection_data={
            "access_token": access_token,
            **connection_data,
        },
    )