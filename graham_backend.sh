#!/bin/bash
./venv/bin/celery -A tasks worker -l info
