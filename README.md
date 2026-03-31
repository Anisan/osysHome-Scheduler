# Scheduler - Task Scheduler Module

![Scheduler Icon](static/Scheduler.png)

A comprehensive task scheduling system for executing code at specified times using cron syntax or one-time execution.

## Description

The `Scheduler` module provides a task scheduling system for the osysHome platform. It enables you to schedule code execution using cron syntax, set one-time tasks, and monitor task execution.

## Main Features

- ✅ **Cron Scheduling**: Schedule tasks using cron syntax
- ✅ **One-Time Tasks**: Execute tasks at specific date/time
- ✅ **Task Management**: Create, edit, delete tasks
- ✅ **Task Monitoring**: Monitor task execution and performance
- ✅ **Thread Pool**: Managed thread pool for task execution
- ✅ **Search Integration**: Search tasks by name or code
- ✅ **Widget Support**: Dashboard widget with task statistics

## Admin Panel

The module provides a comprehensive admin interface:

### Main View
- **Tasks List**: View all scheduled tasks
- **Task Information**: Name, schedule, code, status
- **Actions**: Add, edit, delete tasks
- **Monitoring**: View task execution statistics

### Task Operations

#### Add Task
- Set task name
- Configure schedule (cron or one-time)
- Enter Python code to execute
- Set expiration date
- Activate/deactivate task

#### Edit Task
- Modify task configuration
- Update schedule and code
- Change activation status

#### Delete Task
- Remove task from scheduler
- Clean up task data

## Scheduling

### Cron Syntax
Standard cron format: `minute hour day month weekday`
- Supports second-by-second execution
- Example: `*/5 * * * *` - Every 5 minutes

### One-Time Execution
- Set specific date and time
- Task executes once and expires
- Automatic cleanup after expiration

## Task Monitoring

The module provides task monitoring:
- **Execution Statistics**: Track task execution times
- **Error Tracking**: Monitor task failures
- **Performance Metrics**: Execution time tracking
- **Pool Management**: Monitor thread pool status

## Widget

The module provides a dashboard widget showing:
- Total number of tasks
- Number of active tasks
- Number of cron tasks
- Task monitoring statistics

## Usage

### Creating a Scheduled Task

1. Navigate to Scheduler module
2. Click "Add Task"
3. Enter task name
4. Set cron schedule or one-time execution
5. Enter Python code
6. Save task

### Monitoring Tasks

1. Navigate to Scheduler module
2. Go to "Monitoring" tab
3. View task execution statistics
4. Monitor thread pool status

## Technical Details

- **Thread Pool**: MonitoredThreadPool for task execution
- **Task Storage**: Database storage for tasks
- **Code Execution**: Safe code execution environment
- **Expiration**: Automatic task expiration and cleanup
- **WebSocket**: Real-time task updates

## Version

Current version: **0.6**

## Category

System

## Actions

The module provides the following actions:
- `cycle` - Background task execution
- `search` - Search tasks by name or code
- `widget` - Dashboard widget with statistics

## Requirements

- Flask
- SQLAlchemy
- osysHome core system

## Author

osysHome Team

## License

See the main osysHome project license

