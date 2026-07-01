from app import create_app
from app.extensions import bcrypt, db
from app.models.user import User


app = create_app()


def update_password(email: str, plain_password: str):
    with app.app_context():
        user = User.query.filter_by(email=email).first()

        if not user:
            print("User not found")
            return

        password_hash = bcrypt.generate_password_hash(
            plain_password
        ).decode("utf-8")

        user.password_hash = password_hash
        db.session.commit()

        print("Password updated successfully")
        print("Email:", email)
        print("Hash:", password_hash)


if __name__ == "__main__":
    update_password(
        "owner@gomadwr.com",
        "admin123"
    )