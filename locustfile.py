from locust import HttpUser, task, between

class Reader(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(5)
    def leaderboard(self):
        self.client.get("/leaderboard?limit=10", name="leaderboard")

    @task
    def health(self):
        self.client.get("/health/live")
