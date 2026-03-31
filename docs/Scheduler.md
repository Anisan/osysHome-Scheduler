# User Guide - Scheduler

![Scheduler Icon](../static/Scheduler.png)

The **Scheduler** module runs Python code automatically at a scheduled time. It is used for recurring jobs with cron expressions and for one-time tasks that must run at a specific date and time.

> [!IMPORTANT]
> Only trusted administrators should create or edit scheduler tasks. A task can execute arbitrary Python code inside the system.

## Module purpose

With `Scheduler`, an administrator can:

- create scheduled tasks;
- set a cron schedule for repeated execution;
- configure a one-time execution by date and time;
- specify an expiration date for the task;
- enable or disable a task without deleting it;
- monitor execution history and thread pool activity.

## Where to find it

Open **Administration** and select **Scheduler**.

## Main tabs

The module has two main tabs:

- **Tasks**: the list of configured scheduler tasks;
- **Monitoring**: execution statistics, recent history, and active thread pool jobs.

## What is shown on the Tasks page

The main table usually displays:

- task ID;
- task name;
- code snippet;
- runtime;
- expiration date;
- last started time;
- cron expression;
- active status;
- action buttons.

The top area also includes:

- **Refresh** to reload the list;
- **Add** to create a task;
- **Search** to filter by any visible value in the table.

## Core operations

### Create a task

1. Click **Add**.
2. Enter **Name**.
3. Enter Python code in **Code**.
4. Fill in **Cron** for a recurring task, or **Runtime** for a one-time task.
5. Optionally set **Expire**.
6. Leave **Active** enabled if the task should start working immediately.
7. Click **Submit**.

> [!TIP]
> A practical pattern is to use either `Cron` or `Runtime` for one task. This makes the task intent easier to understand and maintain.

### Edit a task

1. Find the task in the list.
2. Click **Edit**.
3. Update the schedule, code, expiration date, or activation flag.
4. Click **Submit**.

Typical edits include:

- changing the cron expression;
- moving a one-time run to another date;
- updating the Python code;
- extending or removing the expiration date;
- switching the task between active and inactive states.

### Enable or disable a task

1. Open the **Tasks** list.
2. Use the pause button for an active task to disable it.
3. Use the play button for an inactive task to enable it again.

Disabled tasks remain in the list, but they are not executed until re-enabled.

### Delete a task

1. Click the **Delete** button in the task row.
2. Confirm the deletion.

> [!WARNING]
> Deletion removes the task configuration. If you may need the task later, it is safer to disable it first.

## Task fields

### Name

A readable task name shown in the list, monitoring view, and history.

### Code

Python code executed by the scheduler when the task starts.

> [!CAUTION]
> Validate code carefully before saving. Incorrect code can fail repeatedly or affect system behavior.

### Cron

A cron expression for repeated execution.

Format:

`minute hour day month weekday`

The scheduler also supports second-level intervals. In that case, seconds are specified as the sixth parameter.

Extended format:

`minute hour day month weekday second`

Example:

- `*/5 * * * *` - every 5 minutes
- `0 7 * * *` - every day at 07:00
- `* * * * * */10` - every 10 seconds

### Runtime

The date and time for one-time execution.

This is useful when a task must run once, for example for a delayed action or a maintenance step.

### Expire

The date and time after which the task should no longer be considered valid.

This is especially useful for temporary jobs and one-time tasks.

### Active

The current execution state of the task:

- enabled tasks can run;
- disabled tasks stay stored but do not run.

## Monitoring page

The **Monitoring** tab helps track scheduler activity in real time. It usually shows:

- thread pool statistics;
- execution time statistics;
- execution time history chart;
- currently active tasks;
- recent task history with duration and success status.

This page is useful for checking whether tasks are running normally and whether the worker pool is overloaded.

## Typical scenarios

### Run a recurring task

1. Create a task.
2. Add the Python code.
3. Set a cron expression such as `0 * * * *`.
4. Save the task with **Active** enabled.
5. Check the **Monitoring** tab after the expected run time.

### Run a one-time task

1. Create a task.
2. Fill in **Name** and **Code**.
3. Leave **Cron** empty.
4. Set **Runtime** to the required date and time.
5. Optionally set **Expire**.
6. Save the task.

### Pause a problematic task

1. Open the task list.
2. Click the pause button for the task.
3. Review the code and schedule.
4. Re-enable the task only after the issue is resolved.

### Investigate failures

1. Open **Monitoring**.
2. Review recent history.
3. Check task duration and failure status.
4. Open the task and inspect its code and schedule.

## Administrator checklist

- [ ] Every task has a clear and unique name.
- [ ] The Python code has been reviewed before activation.
- [ ] The task uses the correct scheduling method: `Cron` or `Runtime`.
- [ ] Temporary tasks have an expiration date where appropriate.
- [ ] Failed or obsolete tasks are disabled or deleted.
