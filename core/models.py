from dataclasses import dataclass

@dataclass
class JobOffer:
    job_id: str
    title: str
    company: str
    salary: str
    link: str
    platform: str
    timestamp_found: str