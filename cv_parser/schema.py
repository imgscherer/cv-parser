from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: str | None = Field(None, description="YYYY-MM, or YYYY if month unknown")
    end_date: str | None = Field(None, description="YYYY-MM, YYYY, or 'present'")
    description: str | None = None
    highlights: list[str] = []


class Project(BaseModel):
    name: str | None = None
    role: str | None = None
    start_date: str | None = Field(None, description="YYYY-MM, or YYYY if month unknown")
    end_date: str | None = Field(None, description="YYYY-MM, YYYY, or 'present'")
    description: str | None = None
    highlights: list[str] = []
    technologies: list[str] = []


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class Language(BaseModel):
    name: str
    level: str | None = None


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None


_ONGOING = {"present", "current", "atual", "presente"}


def _recency_key(item) -> tuple[int, str]:
    """Sort key: ongoing entries first, then by end date, both descending."""
    end = (item.end_date or "").strip().lower()
    ongoing = end in _ONGOING
    return (1, item.start_date or "") if ongoing else (0, end or item.start_date or "")


class Resume(BaseModel):
    full_name: str | None = None
    headline: str | None = Field(None, description="Current title or professional headline")
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    summary: str | None = None
    skills: list[str] = Field([], description="Technical skills, tools, languages, frameworks")
    soft_skills: list[str] = Field([], description="Interpersonal/behavioral skills, e.g. leadership, teamwork")
    experience: list[Experience] = Field([], description="Jobs and internships only, not projects")
    projects: list[Project] = Field([], description="Items listed under a projects section")
    education: list[Education] = []
    languages: list[Language] = []
    certifications: list[Certification] = []

    def normalize(self) -> "Resume":
        """Dedupe skills (case-insensitive) and sort entries most recent first."""
        for field in ("skills", "soft_skills"):
            seen: dict[str, str] = {}
            for item in getattr(self, field):
                seen.setdefault(item.strip().casefold(), item.strip())
            setattr(self, field, [v for k, v in seen.items() if k])
        for field in ("experience", "projects", "education"):
            setattr(self, field, sorted(getattr(self, field), key=_recency_key, reverse=True))
        return self
