---
name: claude-maxer
description: >
  Trigger this skill when the request contains 'In order to untilize my claude limitation ...',   'to max my claude limitation ...', 
  'as my limitation of claude subscription has xx left ...', '5h', '7d', etc. Users want to leverate their Claude subscriptions. 
  Check if the background script exists, make one if it doesn't. Execute tasks follow the strategies.
---

# Claude-maxer

There is a script running background(claude-maxer/check_usage.py), to check the usage of the claude subscription, when the usage is far behind expectation, we'd like do some routines to consume the limitation of the subscription.

```

Check `crontab -l` for the current state (enabled/disabled and cadence both
change over time — this file is documentation, not the source of truth).

**Enrolling the schedule:** `enroll_cron.sh` manages the entry instead of
hand-editing the crontab. It fires `run_maxer_work.sh` at 03:30, 07:30,
12:30, 17:30 and 22:30 daily (machine-local time, CST):

```

./enroll_cron.sh install # add/replace the managed block (idempotent)
./enroll_cron.sh status # show the managed block, or "Not enrolled."
./enroll_cron.sh remove # drop the block, leave every other entry alone
./enroll_cron.sh print # preview the block without touching crontab

## Strategies

Every period should reach the ceiling, if it didn't do the tasks list below.

| elapsed in the 5h window | ceiling | effect                             |
| ------------------------ | ------- | ---------------------------------- |
| hour 0                   | 0%      | steady — no unattended work at all |
| hour 1                   | 25%     |                                    |
| hour 2                   | 50%     |                                    |
| hour 3                   | 75%     |                                    |
| hour 4                   | 95%     |                                    |
