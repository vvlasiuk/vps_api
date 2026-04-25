
# CLI management for master tokens
from dotenv import load_dotenv
load_dotenv()
import click
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import MasterToken, MasterTokenStatus
from datetime import datetime
import secrets

@click.group()
def cli():
    pass

@cli.command()
def list_tokens():
    """List all master tokens."""
    db: Session = SessionLocal()
    tokens = db.query(MasterToken).all()
    for t in tokens:
        print(f"ID: {t.id} | Token: {t.token} | Status: {t.status.value} | Created: {t.created_at} | Desc: {t.description}")
    db.close()

@cli.command()
@click.option('--description', prompt='Description', help='Description for the token')
def create_token(description):
    """Create a new master token."""
    db: Session = SessionLocal()
    token_str = secrets.token_urlsafe(32)
    token = MasterToken(token=token_str, description=description, status=MasterTokenStatus.active, created_at=datetime.utcnow())
    db.add(token)
    db.commit()
    print(f"Created token: {token.token}")
    db.close()

@cli.command()
@click.argument('token_id', type=int)
def revoke_token(token_id):
    """Revoke a master token by ID."""
    db: Session = SessionLocal()
    token = db.query(MasterToken).filter(MasterToken.id == token_id).first()
    if not token:
        print("Token not found.")
    else:
        token.status = MasterTokenStatus.revoked
        db.commit()
        print(f"Revoked token {token.token}")
    db.close()

if __name__ == '__main__':
    cli()
