"""
Serializers for registration, the current user, and PAN profiles.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .crypto import hash_pan
from .models import PanProfile, pan_validator

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    # write_only keeps the password out of every response. style= only
    # affects how the browsable API renders the input.
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"},
        validators=[validate_password],     # runs AUTH_PASSWORD_VALIDATORS
    )
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "password", "password_confirm"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        # Object-level validate() — for rules that need more than one field.
        # Single-field rules belong in validate_<fieldname>.
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        # Go through the manager so the password is hashed. Calling
        # User.objects.create(**validated_data) would store it in plaintext.
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    pan_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "created_at", "pan_count"]
        read_only_fields = ["id", "email", "created_at", "pan_count"]


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Adds the user's identity to the login response so the frontend does not
    need a second request just to render a name in the header.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Claims are embedded in the JWT itself. Keep them small and never
        # put anything secret here — a JWT is signed, not encrypted, and
        # anyone holding it can read the payload.
        token["email"] = user.email
        token["name"] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class PanProfileSerializer(serializers.ModelSerializer):
    """
    Accepts a full PAN on write, returns only the masked form on read.

    `pan` is write_only and is not a model field — set_pan() on the model
    is what turns it into the three stored columns.
    """

    pan = serializers.CharField(
        # The regex check lives in validate_pan, after normalising case —
        # field-level validators would run first and reject "abcde1234f".
        write_only=True, max_length=10,
        help_text="Ten characters, e.g. ABCDE1234F.",
    )
    pan_masked = serializers.CharField(read_only=True)
    application_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PanProfile
        fields = [
            "id", "label", "pan", "pan_masked", "dp_id",
            "is_active", "application_count", "created_at",
        ]
        read_only_fields = ["id", "pan_masked", "application_count", "created_at"]

    def validate_pan(self, value):
        """
        Reject a PAN this user has already registered.

        The database constraint is the real guarantee; this exists to turn
        what would be a 500 (IntegrityError) into a readable 400.
        """
        value = value.strip().upper()
        pan_validator(value)
        owner = self.context["request"].user
        qs = PanProfile.objects.filter(owner=owner, pan_hash=hash_pan(value))
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)   # editing its own row is fine
        if qs.exists():
            raise serializers.ValidationError("You have already added this PAN.")
        return value

    def create(self, validated_data):
        raw_pan = validated_data.pop("pan")
        instance = PanProfile(owner=self.context["request"].user, **validated_data)
        instance.set_pan(raw_pan)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        raw_pan = validated_data.pop("pan", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if raw_pan:
            instance.set_pan(raw_pan)
        instance.save()
        return instance