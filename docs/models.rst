.. _models_topic:

Models
======

Basics
------

Flask-Security assumes you'll be using libraries such as SQLAlchemy,
MongoEngine, Peewee or PonyORM to define a `User`
and `Role` data model. The fields on your models must follow a particular convention
depending on the functionality your app requires. Aside from this, you're free
to add any additional fields to your model(s) if you want.

.. note::
    The User, Role, and WebAuthn models MUST subclass their respective mixin (along
    with any other mixin the datastore requires). The pre-packaged models described
    below do this for you.

    .. code-block:: python

        from flask_security import UserMixin, RoleMixin, WebAuthMixin

        class User(<db specific base>, UserMixin):
            ... define columns here

        ... same for Role and WebAuthn

Packaged Models
----------------
As more features are added to Flask-Security, the list of required fields and tables grow.
As you use these features, and therefore require these fields and tables, database migrations are required;
which are a bit of a pain. To make things easier - Flask-Security includes mixins that
contain ALL the fields and tables required for all features. They also contain
various `best practice` fields - such as update and create times. These mixins can
be easily extended to add any sort of custom fields and can be found in the
`models` module.

The provided models are versioned since they represent actual DB models, and any
changes require a schema migration (and perhaps a data migration). Applications
must specifically import the version they want (and handle any required migration).

There are 2 available models - one when using Flask-SQLAlchemy and one when
using 'raw' sqlalchemy or Flask-SQLAlchemy-Lite.

.. note::
    Using these models, you can override the tables names (and provide them to .set_db_info()
    however your model class names MUST be `User`, `Role`, and `WebAuthn`.

Flask-SQLAlchemy
^^^^^^^^^^^^^^^^
Your application code should import just the required version e.g.::

    from flask_security.models import fsqla_v3 as fsqla
    from flask_sqlalchemy import SQLAlchemy

    db = SQLAlchemy(app)

    # Define models
    fsqla.FsModels.set_db_info(db)

    class Role(db.Model, fsqla.FsRoleMixin):
        pass

    class User(db.Model, fsqla.FsUserMixin):
        pass


A single method ``fsqla.FsModels.set_db_info`` is provided to glue the supplied models to your
DB instance. This is only needed if you use the packaged models.

Flask-SQLAlchemy-Lite
^^^^^^^^^^^^^^^^^^^^^
Your application code should import just the required version e.g.::

    from flask_security.models import sqla as sqla
    from flask_sqlalchemy_lite import SQLAlchemy

    db = SQLAlchemy(app)

    # Define models
    class Model(DeclarativeBase):
        pass

    # NOTE: call this PRIOR to declaring models
    sqla.FsModels.set_db_info(base_model=Model)

    class Role(Model, sqla.FsRoleMixin):
        __tablename__ = "Role"
        pass

    class User(Model, sqla.FsUserMixin):
        __tablename__ = "User"
        pass

A single method ``sqla.FsModels.set_db_info`` is provided to glue the supplied mixins to your
models. This is only needed if you use the packaged models.

.. note::
    This model requires Python >= 3.10.

Model Specification
-------------------

Your `User` model needs a Primary Key - Flask-Security doesn't actually reference
this - so it can be any name or type your application needs. It should be used in the
foreign relationship between `User` and `Role`. The `WebAuthn` model also
references this primary key (which can be overridden by providing a
suitable implementation of :py:meth:`flask_security.WebAuthnMixin.get_user_mapping`).

At the bare minimum your `User` and `Role` model must include the following fields:

**User**

* primary key
* ``email`` (for most features - unique, non-nullable)
* ``password`` (string, nullable)
* ``active`` (boolean, non-nullable)
* ``fs_uniquifier`` (string, 64 bytes, unique, non-nullable)
* a many-to-many relationship to table Role


**Role**

* primary key
* ``name`` (unique, non-nullable)
* ``description`` (string)
* a many-to-many relationship to table User


Additional Functionality
------------------------

Depending on the application's configuration, additional fields may need to be
added to your database models. Note some fields are specified as 'list of string'
the ORM you are using is responsible for translating the list of string to a suitable
DB data type. For standard SQL-like databases, Flask-Security provides a utility
method :class:`.AsaList`.

Confirmable
^^^^^^^^^^^

If you enable account confirmation by setting your application's
:py:data:`SECURITY_CONFIRMABLE` or :py:data:`SECURITY_CHANGE_EMAIL` configuration value to `True`,
your `User` model will require the following additional field:

* ``confirmed_at`` (datetime)

Trackable
^^^^^^^^^

If you enable user tracking by setting your application's :py:data:`SECURITY_TRACKABLE`
configuration value to `True`, your `User` model will require the following
additional fields:

* ``last_login_at`` (datetime)
* ``current_login_at`` (datetime)
* ``last_login_ip`` (string)
* ``current_login_ip`` (string)
* ``login_count`` (integer)

Two_Factor
^^^^^^^^^^

If you enable two-factor by setting your application's :py:data:`SECURITY_TWO_FACTOR`
configuration value to `True`, your `User` model will require the following
additional fields:

* ``tf_totp_secret`` (string, 255 bytes, nullable)
* ``tf_primary_method`` (string)

If you include 'sms' in :py:data:`SECURITY_TWO_FACTOR_ENABLED_METHODS`, your `User` model
will require the following additional field:

* ``tf_phone_number`` (string, 128 bytes, nullable)

Unified Sign In
^^^^^^^^^^^^^^^

If you enable unified sign in by setting your application's :py:data:`SECURITY_UNIFIED_SIGNIN`
configuration value to `True`, your `User` model will require the following
additional fields:

* ``us_totp_secrets`` (an arbitrarily long Text field)

If you include 'sms' in :py:data:`SECURITY_US_ENABLED_METHODS`, your `User` model
will require the following additional field:

* ``us_phone_number`` (string, 64 bytes, nullable, unique)

Separate Identity Domains
^^^^^^^^^^^^^^^^^^^^^^^^^
If you want authentication tokens to not be invalidated when the user changes their
password add the following to your `User` model:

* ``fs_token_uniquifier`` (string, 64 bytes, unique, non-nullable)

Username
^^^^^^^^
If you set :py:data:`SECURITY_USERNAME_ENABLE` to `True`, then your `User` model
requires the following additional field:

* ``username`` (string, 64 bytes, unique, nullable)

Permissions
^^^^^^^^^^^
If you want to protect endpoints with permissions, and assign permissions to roles
that are then assigned to users, the ``Role`` model requires:

* ``permissions`` (list of UnicodeText, nullable)

.. _webauthn_model:

WebAuthn
^^^^^^^^
Flask Security can act as a WebAuthn Relying Party by enabling
:py:data:`SECURITY_WEBAUTHN`. This requires an additional table as well as
references from the User model. Users can have many WebAuthn credentials, and
Flask-Security must be able to locate a User record based on a credential id.

.. important::
    It is important that you maintain data consistency when deleting WebAuthn
    records or users.

The 'WebAuthn' model requires the following fields:

* ``id`` (primary key)
* ``credential_id`` (binary, 1024 bytes, indexed, non-nullable, unique)
* ``public_key`` (binary, 1024 bytes, non-nullable)
* ``sign_count`` (integer, default=0, non-nullable)
* ``transports`` (list of string/UnicodeText, nullable)
* ``extensions`` (string, 255 bytes)
* ``lastuse_datetime`` (datetime, non-nullable)
* ``name`` (string, 64 bytes, non-nullable)
* ``usage`` (string, 64 bytes, non-nullable)
* ``backup_state`` (boolean, non-nullable)
* ``device_type`` (string, 64 bytes, non-nullable) (The spec calls this ``Backup Eligibility``)

There needs to be a bi-directional relationship between the WebAuthn record and
the User record (since we need to look up the ``User`` based on a WebAuthn ``credential_id``.

**For SQLAlchemy**::

    Add the following to the WebAuthn model (assuming your primary key is named ``id``):

        @declared_attr
        def user_id(cls) -> Mapped[int]:
            return mapped_column(
                ForeignKey("user.id", ondelete="CASCADE")
            )

    Add the following to the User model:

        @declared_attr
        def webauthn(cls):
            return relationship(
                "WebAuthn", back_populates="user", cascade="all, delete"
            )

**For mongoengine**::

    Add the following to the WebAuthn model:

        user = ReferenceField("User")
        def get_user_mapping(self) -> dict[str, str]:
            """Return the mapping from webauthn back to User"""
            return dict(id=self.user.id)

    Add the following to the User model:

        webauthn = ListField(ReferenceField(WebAuthn, reverse_delete_rule=PULL), default=[])

    To make sure all WebAuthn objects are deleted if the User is deleted:

        User.register_delete_rule(WebAuthn, "user", CASCADE)


**For peewee**::

    Add the following to the WebAuthn model:

        user = ForeignKeyField(User, backref="webauthn")

    This will add a column called ``user_id`` that references the User model's
    ``id`` primary key field. It will also create a virtual column ``webauthn``
    as part of the User model. Note that the default Peewee datastore implementation
    calls ``delete_instance(recursive=True)`` which correctly deals with ensuring
    that WebAuthn records get deleted if a User is deleted.

The `User` model needs the following additional fields:

* ``fs_webauthn_user_handle`` (string, 64 bytes, unique).
  This is used as the `PublicKeyCredentialUserEntity` `id` value.

Recovery Codes
^^^^^^^^^^^^^^^
If :py:data:`SECURITY_MULTI_FACTOR_RECOVERY_CODES` is set to ``True`` then
the `User` model needs the following field:

* ``mf_recovery_codes`` (list of string/UnicodeText, nullable)

A recovery code can be used in place of any configured second-factor authenticator
(e.g. SMS, WebAuthn, ...).

Custom User Payload
^^^^^^^^^^^^^^^^^^^

If you want a custom payload for JSON API responses, define
the method `get_security_payload` in your User model. The method must return a
serializable object:

.. code-block:: python

    class User(db.Model, UserMixin):
        # ... define columns ...

        # Custom User Payload
        def get_security_payload(self):
            rv = super().get_security_payload()
            # :meth:`User.calc_username`
            rv["username"] = self.calc_username()
            rv["confirmation_needed"] = self.confirmed_at is None
            return rv
