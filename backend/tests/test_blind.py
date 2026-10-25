import pytest

from app.blind import PLACEHOLDER, neutralise_pronouns, redact
from app.models import BlindProfile, Education, Experience, Identity, ParsedResume, Project


def make_parsed(identity: Identity | None = None, **profile_overrides) -> ParsedResume:
    profile = dict(
        headline="Priya Sharma, backend engineer, 4 yrs, Python/Go. She is based in Pune.",
        education=[
            Education(institution="College of Engineering Pune", degree="B.Tech", field="Computer Science",
                      grade="8.7/10 CGPA", start_year=2016, end_year=2020),
            Education(institution="Delhi Public School", degree="Class XII", field=None,
                      grade="92%", start_year=None, end_year=2016),
        ],
        experience=[
            Experience(title="Software Engineer", organisation="Infosys", start="2020-07", end="present", months=51,
                       summary="Ms. Sharma built payment APIs in Go; her team shipped 3 services in 2021-2023. "
                               "Reach her at priya.sharma@gmail.com or +91 98765 43210. "
                               "The manager promoted her to lead."),
        ],
        total_experience_months=51,
        skills=["Python", "Go", "ASP.NET/C#", "github.com/priyasharma", "SQL"],
        projects=[Project(title="Pune Traffic Analyzer",
                          summary="PRIYA built a dashboard; see https://priyasharma.dev/traffic.")],
        certifications=["AWS Certified Developer"],
    )
    profile.update(profile_overrides)
    return ParsedResume(
        identity=identity or Identity(
            name="Priya Sharma",
            email="priya.sharma@gmail.com",
            phone="+91 98765 43210",
            links=["https://www.linkedin.com/in/priya-sharma-dev", "https://github.com/priyasharma"],
            location="Pune, Maharashtra",
        ),
        profile=BlindProfile(**profile),
        photo_present=False,
    )


NO_IDENTITY = Identity(name=None, email=None, phone=None, links=[], location=None)


def headline_only(headline: str, identity: Identity = NO_IDENTITY) -> ParsedResume:
    """A profile whose only text is the headline, so counts reflect just that string."""
    return make_parsed(identity=identity, headline=headline, education=[], experience=[],
                       skills=[], projects=[], certifications=[])


@pytest.fixture
def result():
    return redact(make_parsed())


def text_of(profile: BlindProfile) -> str:
    return profile.model_dump_json()


def test_removes_full_first_and_last_name_case_insensitive(result):
    profile, _, _ = result
    lowered = text_of(profile).lower()
    assert "priya" not in lowered
    assert "sharma" not in lowered


def test_removes_email_phone_and_urls(result):
    blob = text_of(result[0])
    assert "@" not in blob
    assert "98765" not in blob and "43210" not in blob
    assert "github.com" not in blob and "linkedin" not in blob and "priyasharma.dev" not in blob


def test_removes_location_from_free_text(result):
    profile = result[0]
    assert "Pune" not in profile.headline
    assert "Pune" not in profile.projects[0].title
    assert "Maharashtra" not in text_of(profile)


def test_location_inside_institution_name_is_kept(result):
    # College is visible by policy; city names inside institution names are not scrubbed.
    assert result[0].education[0].institution == "College of Engineering Pune"


def test_neutralises_pronouns_and_titles(result):
    summary = result[0].experience[0].summary
    padded = f" {summary} "
    for word in (" she ", " her ", " he ", " his ", "Ms."):
        assert word not in padded
    assert "their team" in summary
    assert "promoted them to lead" in summary
    assert "They are based" in result[0].headline


def test_keeps_academics_and_employer(result):
    edu, school = result[0].education
    assert (edu.institution, edu.degree, edu.field, edu.grade) == (
        "College of Engineering Pune", "B.Tech", "Computer Science", "8.7/10 CGPA")
    assert (edu.start_year, edu.end_year) == (2016, 2020)
    assert school.grade == "92%" and school.end_year == 2016
    exp = result[0].experience[0]
    assert (exp.organisation, exp.title, exp.start, exp.end, exp.months) == (
        "Infosys", "Software Engineer", "2020-07", "present", 51)
    assert "2021-2023" in exp.summary
    assert result[0].certifications == ["AWS Certified Developer"]


def test_url_only_list_items_are_dropped_and_lookalike_skills_kept(result):
    assert result[0].skills == ["Python", "Go", "ASP.NET/C#", "SQL"]


def test_identity_is_returned_unchanged(result):
    _, identity, _ = result
    assert identity.name == "Priya Sharma"
    assert identity.phone == "+91 98765 43210"
    assert identity.location == "Pune, Maharashtra"


def test_redaction_count_is_exact():
    parsed = make_parsed(
        identity=Identity(name="John Smith", email="john@example.com", phone=None, links=[], location="Austin, Texas"),
        headline="John Smith, Austin, Texas. He is skilled. Mail john@example.com",
        # 1 email + 1 full name + 1 full location + 1 pronoun = 4
        education=[],
        experience=[Experience(title="Engineer", organisation="Acme", start="2020", end="2022", months=24,
                               summary="Mr. Smith moved to Austin; his work: blacksmithing.")],
        # 1 title + 1 token "Smith" + 1 location part "Austin" + 1 pronoun = 4
        # ("blacksmithing" is not a whole-word match for "Smith")
        skills=["Go"],
        projects=[],
        certifications=[],
    )
    profile, _, count = redact(parsed)
    assert count == 8
    assert profile.headline == f"{PLACEHOLDER}. They are skilled. Mail {PLACEHOLDER}"
    assert profile.experience[0].summary == f"{PLACEHOLDER} moved to {PLACEHOLDER}; their work: blacksmithing."


def test_clean_profile_is_untouched():
    parsed = make_parsed(
        identity=Identity(name=None, email=None, phone=None, links=[], location=None),
        headline="Data analyst, 3 yrs, SQL/Tableau",
        experience=[Experience(title="Analyst", organisation="Acme", start="2021", end="present", months=40,
                               summary="Built weekly revenue dashboards used by 40 managers.")],
        skills=["SQL", "Tableau"],
        projects=[],
    )
    profile, _, count = redact(parsed)
    assert count == 0
    assert profile == parsed.profile


def test_name_tokens_match_whole_words_only():
    parsed = make_parsed(
        identity=Identity(name="Ann Lee", email=None, phone=None, links=[], location=None),
        headline="Planning lead at Leeds office; Ann and LEE ran it",
        projects=[],
    )
    profile, _, _ = redact(parsed)
    assert profile.headline.startswith("Planning lead at Leeds office;")
    assert "Ann" not in profile.headline and "LEE" not in profile.headline


def test_name_tokens_of_two_chars_are_ignored_but_full_name_removed():
    parsed = make_parsed(
        identity=Identity(name="Li Wu", email=None, phone=None, links=[], location=None),
        headline="Li Wu: ML engineer using Wu-style naming and li elements",
        projects=[],
    )
    profile, _, _ = redact(parsed)
    assert profile.headline == f"{PLACEHOLDER}: ML engineer using Wu-style naming and li elements"


@pytest.mark.parametrize("phone", [
    "+91 98765 43210", "+91-9876543210", "+919876543210", "+1 (555) 123-4567", "(555) 123-4567",
    "555-123-4567", "555.123.4567", "+44 20 7946 0958", "9876543210", "98765 43210",
])
def test_phone_formats_are_removed(phone):
    profile, _, count = redact(headline_only(f"Call {phone} today"))
    assert profile.headline == f"Call {PLACEHOLDER} today"
    assert count == 1


@pytest.mark.parametrize("text", [
    "2019-2023", "2015 - 2019", "Python 3.11 2020 2021 2022", "8.7/10 CGPA", "78%", "1,200,000 users",
    "MS in Computer Science", "B.Tech/M.Tech", "ASP.NET/VB.NET", "Node.js, Vue.js", "HIS (Hospital Information System)",
    "Never miss a deadline", "GitHub Actions",
])
def test_lookalikes_are_not_redacted(text):
    profile, _, count = redact(headline_only(text))
    assert profile.headline == text
    assert count == 0


def test_identity_phone_in_unusual_format_is_removed():
    identity = Identity(name=None, email=None, phone="+91 98765 43210", links=[], location=None)
    profile, _, _ = redact(headline_only("Phone: 98-765-432-10", identity))
    assert "98" not in profile.headline


@pytest.mark.parametrize("before, after", [
    ("She led her team.", "They led their team."),
    ("The board promoted her to director.", "The board promoted them to director."),
    ("He is an engineer and he was promoted.", "They are an engineer and they were promoted."),
    ("He has shipped it himself.", "They have shipped it themselves."),
    ("The design was hers.", "The design was theirs."),
    ("His code; thanked her.", "Their code; thanked them."),
])
def test_neutralise_pronouns(before, after):
    text, n = neutralise_pronouns(before)
    assert text == after
    assert n >= 1


def test_strings_without_redactions_keep_exact_formatting():
    text = "Skills : Python ,  SQL\n\nLed 3 teams"
    profile, _, count = redact(headline_only(text))
    assert profile.headline == text
    assert count == 0


def test_leak_check_finds_identity_only_when_present(result):
    from app.leaks import find_leaks

    profile, identity, _ = result
    assert find_leaks(profile.model_dump(), identity) == []
    leaky = make_parsed().profile.model_dump()  # before redaction
    found = find_leaks(leaky, identity)
    assert "Priya Sharma" in found and "priya.sharma@gmail.com" in found and any(f.startswith("phone") for f in found)
