from io import BytesIO

import pytest
from flask import json
from flask import request
from werkzeug.datastructures import FileStorage
from werkzeug.datastructures import MultiDict
from wtforms import StringField
from wtforms.validators import DataRequired
from wtforms.validators import Length

from flask_wtf import CSRFProtect
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from flask_wtf.file import FileField
from flask_wtf.file import FileSize
from flask_wtf.recaptcha import RecaptchaField
from flask_wtf.recaptcha.validators import http

pytest.importorskip("flask_wtf.i18n", reason="Flask-Babel is not installed.")


class NameForm(FlaskForm):
    class Meta:
        csrf = False

    name = StringField(validators=[DataRequired(), Length(min=8)])


@pytest.fixture
def fr_app(app):
    pytest.importorskip("flask_babel")
    from flask_babel import Babel

    Babel(app, locale_selector=lambda: "fr")
    return app


def test_no_extension(app, client):
    @app.route("/", methods=["POST"])
    def index():
        form = NameForm()
        form.validate()
        assert form.name.errors[0] == "This field is required."

    client.post("/", headers={"Accept-Language": "zh-CN,zh;q=0.8"})


def test_i18n(app, client):
    try:
        from flask_babel import Babel
    except ImportError:
        pytest.skip("Flask-Babel must be installed.")

    def get_locale():
        return request.accept_languages.best_match(["en", "zh"], "en")

    Babel(app, locale_selector=get_locale)

    @app.route("/", methods=["POST"])
    def index():
        form = NameForm()
        form.validate()

        if not app.config.get("WTF_I18N_ENABLED", True):
            assert form.name.errors[0] == "This field is required."
        elif not form.name.data:
            assert form.name.errors[0] == "该字段是必填字段。"
        else:
            assert form.name.errors[0] == "字段长度必须至少 8 个字符。"

    client.post("/", headers={"Accept-Language": "zh-CN,zh;q=0.8"})
    client.post("/", headers={"Accept-Language": "zh"}, data={"name": "short"})
    app.config["WTF_I18N_ENABLED"] = False
    client.post("/", headers={"Accept-Language": "zh"})


def test_outside_request():
    pytest.importorskip("babel")
    from flask_wtf.i18n import translations

    s = "This field is required."
    assert translations.gettext(s) == s

    ss = "Field must be at least %(min)d character long."
    sp = "Field must be at least %(min)d character long."
    assert translations.ngettext(ss, sp, 1) == ss
    assert translations.ngettext(ss, sp, 2) == sp


def test_i18n_recaptcha(fr_app, monkeypatch):
    fr_app.testing = False
    fr_app.config["RECAPTCHA_PUBLIC_KEY"] = "public"
    fr_app.config["RECAPTCHA_PRIVATE_KEY"] = "private"

    class _Resp:
        code = 200

        def read(self):
            return json.dumps(
                {"success": False, "error-codes": ["missing-input-secret"]}
            )

    monkeypatch.setattr(http, "urlopen", lambda url, data: _Resp())

    class RecaptchaForm(FlaskForm):
        class Meta:
            csrf = False

        recaptcha = RecaptchaField()

    with fr_app.test_request_context(data={"g-recaptcha-response": "x"}):
        form = RecaptchaForm()
        form.validate()
        assert form.recaptcha.errors[0] == "Le paramètre secret est manquant."


def test_i18n_csrf_form(fr_app, client):
    fr_app.config["WTF_CSRF_ENABLED"] = True

    class CsrfForm(FlaskForm):
        name = StringField()

    @fr_app.route("/", methods=["POST"])
    def index():
        form = CsrfForm()
        form.validate()
        assert form.csrf_token.errors[0] == "Le jeton CSRF est manquant."
        return ""

    client.post("/")


def test_i18n_csrf_form_respects_wtf_i18n_enabled(fr_app, client):
    fr_app.config["WTF_CSRF_ENABLED"] = True
    fr_app.config["WTF_I18N_ENABLED"] = False

    class CsrfForm(FlaskForm):
        name = StringField()

    @fr_app.route("/", methods=["POST"])
    def index():
        form = CsrfForm()
        form.validate()
        assert form.csrf_token.errors[0] == "The CSRF token is missing."
        return ""

    client.post("/")


def test_i18n_csrf_protect(fr_app, client):
    CSRFProtect(fr_app)

    @fr_app.route("/", methods=["POST"])
    def index():
        return ""

    response = client.post("/")
    assert response.status_code == 400
    assert b"Le jeton CSRF est manquant." in response.data


def test_i18n_file_allowed(fr_app):
    class UploadForm(FlaskForm):
        class Meta:
            csrf = False

        file = FileField(validators=[FileAllowed(("txt",))])

    with fr_app.test_request_context():
        form = UploadForm(
            MultiDict((("file", FileStorage(stream=BytesIO(b"x"), filename="a.jpg")),))
        )
        form.validate()
        assert form.file.errors[0] == "Le fichier n'a pas une extension autorisée : txt"


def test_i18n_file_size(fr_app):
    class UploadForm(FlaskForm):
        class Meta:
            csrf = False

        file = FileField(validators=[FileSize(max_size=10)])

    with fr_app.test_request_context():
        form = UploadForm(
            MultiDict(
                (("file", FileStorage(stream=BytesIO(b"x" * 100), filename="a.txt")),)
            )
        )
        form.validate()
        assert form.file.errors[0] == "Le fichier doit faire entre 0 et 10 octets."
