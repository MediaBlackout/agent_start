#!/usr/bin/env python3
"""
todo_cli.py

A command-line interface (CLI) for managing a simple to-do list stored in a plain text file (tasks.txt).
Supports adding, listing, deleting, and completing tasks.

Usage Examples:
    python todo_cli.py add "Buy groceries"
    python todo_cli.py list
    python todo_cli.py delete 2
    python todo_cli.py complete 1
"""

import argparse
import os
import sys

TASKS_FILE = "tasks.txt"

def load_tasks():
    """
    Loads tasks from the tasks.txt file.

    Returns:
        list: A list of task strings.
    """
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as file:
            tasks = [line.strip() for line in file if line.strip()]
        return tasks
    except FileNotFoundError:
        return []

def save_tasks(tasks):
    """
    Saves the list of tasks to the tasks.txt file.

    Args:
        tasks (list): A list of task strings to be saved.
    """
    try:
        with open(TASKS_FILE, 'w', encoding='utf-8') as file:
            for task in tasks:
                file.write(task + '\n')
    except IOError as e:
        print(f"Error: Unable to write to {TASKS_FILE}: {e}")

def add_task(task_description):
    """
    Adds a new task to the tasks.txt file.

    Args:
        task_description (str): The task description to be added.
    """
    try:
        with open(TASKS_FILE, 'a', encoding='utf-8') as file:
            file.write(task_description + '\n')
        print(f"Task added: \"{task_description}\"")
    except IOError as e:
        print(f"Error: Cannot add task: {e}")

def list_tasks():
    """
    Lists all tasks from the tasks.txt file with numbering.
    """
    tasks = load_tasks()
    if not tasks:
        print("No tasks found.")
    else:
        for idx, task in enumerate(tasks, start=1):
            print(f"{idx}. {task}")

def delete_task(task_number):
    """
    Deletes a task at the given one-based index.

    Args:
        task_number (int): The task number (1-based index) to delete.
    """
    tasks = load_tasks()
    if 1 <= task_number <= len(tasks):
        removed_task = tasks.pop(task_number - 1)
        save_tasks(tasks)
        print(f"Task deleted: \"{removed_task}\"")
    else:
        print(f"Error: Task number {task_number} not found.")

def complete_task(task_number):
    """
    Marks a task as complete by prepending '[DONE]' if not already done.

    Args:
        task_number (int): The task number (1-based index) to mark as complete.
    """
    tasks = load_tasks()
    if 1 <= task_number <= len(tasks):
        task = tasks[task_number - 1]
        if not task.startswith("[DONE]"):
            tasks[task_number - 1] = f"[DONE] {task}"
            save_tasks(tasks)
            print(f"Task marked as complete: \"{tasks[task_number - 1]}\"")
        else:
            print(f"Task already marked as complete: \"{task}\"")
    else:
        print(f"Error: Task number {task_number} not found.")

def parse_args():
    """
    Parses command-line arguments using argparse.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Simple CLI To-Do List Application")
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("task", help="The description of the task")

    # List command
    subparsers.add_parser("list", help="List all tasks")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument(
        "number", type=int, help="The task number to delete (1-based index)")

    # Complete command
    complete_parser = subparsers.add_parser(
        "complete", help="Mark a task as complete")
    complete_parser.add_argument(
        "number", type=int, help="The task number to complete (1-based index)")

    return parser.parse_args()

def main():
    """
    Main entry point of the script. Dispatches the appropriate function based on the command.
    """
    # Create tasks.txt if it doesn't exist
    if not os.path.exists(TASKS_FILE):
        open(TASKS_FILE, 'w').close()

    args = parse_args()

    if args.command == "add":
        add_task(args.task)
    elif args.command == "list":
        list_tasks()
    elif args.command == "delete":
        delete_task(args.number)
    elif args.command == "complete":
        complete_task(args.number)
    else:
        # This branch is technically unreachable because subparsers are required
        print("Invalid command.")

if __name__ == "__main__":
    main()
