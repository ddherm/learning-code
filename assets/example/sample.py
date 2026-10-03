from dataclasses import dataclass

@dataclass(frozen=True)
class Job:
    message: str

def build_request(job: Job) -> dict:
    return {"role": "user", "content": job.message}

async def run(job: Job, client) -> str:
    response = await client.create(build_request(job))
    return response.strip()
