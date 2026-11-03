import re

from sqlalchemy import func

from extensions import db
from models import Client, DistributionContact


LIST_TYPES = ("b2b", "individual")


def normalize_email(value):
    email = str(value or "").strip().casefold()
    if len(email) > 255 or not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
        return None
    return email


def distribution_lists():
    contacts = {}
    for contact in DistributionContact.query.order_by(DistributionContact.id).all():
        email = normalize_email(contact.email)
        if email and contact.list_type in LIST_TYPES:
            contacts.setdefault((contact.list_type, email), {
                "id": contact.id, "email": email, "client_id": None,
            })

    for client in Client.query.filter(Client.email.isnot(None)).order_by(Client.id).all():
        email = normalize_email(client.email)
        if email and client.type in LIST_TYPES:
            contact = contacts.setdefault((client.type, email), {
                "id": None, "email": email, "client_id": client.id,
            })
            contact["client_id"] = client.id

    return {
        list_type: [contact for (kind, _), contact in sorted(contacts.items()) if kind == list_type]
        for list_type in LIST_TYPES
    }


def add_distribution_contact(list_type, email):
    existing = DistributionContact.query.filter(
        DistributionContact.list_type == list_type,
        func.lower(func.trim(DistributionContact.email)) == email,
    ).first()
    if existing is None:
        db.session.add(DistributionContact(list_type=list_type, email=email))
