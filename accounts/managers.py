"""
Custom manager for the User model.

Django's default UserManager has `username` hardwired into create_user and
create_superuser. Our users log in with email and have no username, so the
manager has to be replaced — `createsuperuser` calls it directly.
"""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Creates users keyed on email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")

        # Lowercases the domain half of the address so that
        # Jaya@Example.COM and jaya@example.com don't become two accounts.
        email = self.normalize_email(email)

        user = self.model(email=email, **extra_fields)

        # set_password hashes through Django's configured hasher
        # (PBKDF2 by default) and stores the result in user.password.
        # Assigning user.password = raw would store the plaintext.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        # Guard rather than silently override: if someone calls
        # create_superuser(is_staff=False) that is a bug, not a preference.
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)