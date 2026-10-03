"""
User and PAN profile models.
"""

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

from .crypto import decrypt_pan, encrypt_pan, hash_pan, mask_pan
from .managers import UserManager

# Five letters, four digits, one letter: ABCDE1234F.
# The fourth letter encodes holder type (P = individual, C = company…)
# and the fifth is the first letter of the surname.
PAN_REGEX = r"^[A-Z]{5}[0-9]{4}[A-Z]$"
pan_validator = RegexValidator(
    PAN_REGEX,
    message="A PAN is five letters, four digits, then one letter — like ABCDE1234F.",
)


class User(AbstractUser):
    """
    Email-as-username user.

    Subclassing AbstractUser (not AbstractBaseUser) keeps Django's
    permissions, groups and admin integration while letting us drop the
    username column and add our own fields.
    """

    username = None  # removes the column from the table entirely
    email = models.EmailField("email address", unique=True)
    full_name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    # Fields `createsuperuser` prompts for *in addition to* USERNAME_FIELD
    # and password. Email is already the username field, so this is empty.
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email


class PanProfile(models.Model):
    """
    One PAN belonging to one user — themselves, a spouse, a parent.

    The PAN itself is never stored in plaintext. See accounts/crypto.py for
    why there are three columns instead of one.
    """

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="pans",
    )
    label = models.CharField(
        max_length=80,
        help_text="How you refer to this applicant, e.g. 'Self' or 'Father'.",
    )
    pan_encrypted = models.BinaryField(editable=False)
    pan_hash = models.CharField(max_length=64, editable=False, db_index=True)
    pan_masked = models.CharField(max_length=10, editable=False)

    dp_id = models.CharField(
        "demat / DP ID",
        max_length=20,
        blank=True,
        help_text="Optional. Helps you match an allotment to the right account.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to stop including this PAN in new applications.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pan_profiles"
        ordering = ["label"]
        constraints = [
            # The real-world rule: one application per PAN per issue. That
            # is enforced on Application, but a user should not be able to
            # register the same PAN twice either.
            models.UniqueConstraint(
                fields=["owner", "pan_hash"],
                name="uniq_pan_per_owner",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.pan_masked})"

    # ---------------------------------------------------- PAN accessors

    def set_pan(self, raw_pan: str) -> None:
        """
        Assign a PAN, populating all three derived columns at once.

        Always go through this rather than touching the columns directly —
        it is what keeps the ciphertext, hash and mask in agreement.
        """
        raw_pan = raw_pan.strip().upper()
        pan_validator(raw_pan)
        self.pan_encrypted = encrypt_pan(raw_pan)
        self.pan_hash = hash_pan(raw_pan)
        self.pan_masked = mask_pan(raw_pan)

    @property
    def pan(self) -> str:
        """
        The plaintext PAN. Only call this where the full value is genuinely
        needed — an allotment lookup, a CSV the user explicitly exported.
        Never expose it through a serializer.
        """
        return decrypt_pan(self.pan_encrypted)