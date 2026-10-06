import json
from locust import HttpUser, between, task


class VersusLabRaceUser(HttpUser):
    """Simulates realistic users launching multi-model races over SSE streams."""

    wait_time = between(1.0, 3.0)
    token: str = ""

    def on_start(self) -> None:
        """Authenticate as admin to obtain JWT bearer token for the session."""
        resp = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "versuslab123"},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")

    @task(3)
    def test_mock_race_stream(self) -> None:
        """Executes a 5-model mock race and streams all SSE events to completion."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        payload = {
            "prompt": "Compare functional and object-oriented programming paradigms in 3 concise bullet points.",
            "models": ["mock:m1", "mock:m2", "mock:m3", "mock:m4", "mock:m5"],
        }

        with self.client.post(
            "/api/races",
            json=payload,
            headers=headers,
            stream=True,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Race start failed with status {response.status_code}")
                return

            completed_count = 0
            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if line_str.startswith("data:"):
                    try:
                        event = json.loads(line_str[5:].strip())
                        if event.get("type") == "race.completed":
                            completed_count += 1
                    except Exception:
                        pass

            if completed_count > 0:
                response.success()
            else:
                response.failure("Stream ended without race.completed event")

    @task(1)
    def test_health_endpoint(self) -> None:
        """Hits public health check."""
        self.client.get("/api/health")

    @task(1)
    def test_metrics_endpoint(self) -> None:
        """Hits public metrics endpoint."""
        self.client.get("/api/metrics")
