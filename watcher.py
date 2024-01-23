import datetime
import sys
import time
import zoneinfo
from dataclasses import dataclass
from typing import List

import requests
from environs import Env

env = Env()

JIRA_BASE_URL = env.str("JIRA_BASE_URL")
JIRA_USERNAME = env.str("JIRA_USERNAME")
JIRA_TOKEN = env.str("JIRA_TOKEN")
JIRA_PROJECT_IDS = env.list("JIRA_PROJECT_IDS")
JIRA_JQL_DATETIME_FORMAT = env.str("JIRA_DATETIME_FORMAT", "%Y-%m-%d %H:%M")
JIRA_DATETIME_FORMAT = env.str("JIRA_DATETIME_FORMAT", "%Y-%m-%dT%H:%M:%S.%f%z")

SLACK_URL = "https://slack.com/api/chat.postMessage"
SLACK_CHANNEL = env.str("SLACK_CHANNEL")
SLACK_TOKEN = env.str("SLACK_TOKEN")

JIRA_AUTH = (JIRA_USERNAME, JIRA_TOKEN)


@dataclass
class JiraTicket:
    id: str
    title: str
    type: str
    author: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @property
    def url(self):
        return f"{JIRA_BASE_URL}/browse/{self.id}"


def get_timezone():
    resp = requests.get(f"{JIRA_BASE_URL}/rest/api/latest/myself", auth=JIRA_AUTH)
    resp.raise_for_status()

    return zoneinfo.ZoneInfo(resp.json()["timeZone"])


def get_tickets(project_ids: list[str], created_after: datetime.datetime) -> List[JiraTicket]:
    timezone = created_after.tzinfo

    query = f"created >= '{created_after.strftime(JIRA_JQL_DATETIME_FORMAT)}' AND project in {tuple(project_ids)}"

    resp = requests.get(f"{JIRA_BASE_URL}/rest/api/latest/search", {"jql": query}, auth=JIRA_AUTH)
    resp.raise_for_status()

    tickets = resp.json()["issues"]

    return [
        JiraTicket(
            id=t["key"],
            title=t["fields"]["summary"],
            type=t["fields"]["issuetype"]["name"].lower(),
            author=t["fields"]["reporter"]["displayName"],
            created_at=datetime.datetime.strptime(t["fields"]["created"], JIRA_DATETIME_FORMAT).astimezone(timezone),
            updated_at=datetime.datetime.strptime(t["fields"]["updated"], JIRA_DATETIME_FORMAT).astimezone(timezone),
        )
        for t in tickets
    ]


def main(created_after: datetime.datetime):
    tickets = get_tickets(JIRA_PROJECT_IDS, created_after)
    if not tickets:
        print("No tickets found")
        print()
        return

    for t in tickets:
        print(f"Sending Slack notification for ticket {t.url}")
        send_slack_message(t)


def send_slack_message(ticket: JiraTicket) -> None:
    text = f"New {ticket.type} by *{ticket.author}*: <{ticket.url}|*{ticket.title}*>"

    resp = requests.post(
        SLACK_URL,
        json={"channel": SLACK_CHANNEL, "text": text},
        headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
    )
    resp.raise_for_status()


if __name__ == "__main__":
    sleep_time = int(sys.argv[1])

    timezone = get_timezone()

    last_created_after = None

    while True:
        now = datetime.datetime.now(tz=timezone)

        if last_created_after is None:
            created_after = now - datetime.timedelta(seconds=sleep_time)
        else:
            created_after = last_created_after

        print(f"All datetimes are in timezone {timezone}")
        print(f"Current time: {now}")
        print(f"Searching for tickets created after {created_after}")
        print()

        try:
            main(created_after)
        except Exception as e:
            print(e)
        else:
            last_created_after = now

        print(f"Sleeping for {int(sleep_time / 60)} minutes")
        print()
        print()
        time.sleep(sleep_time)
