"""
Standalone activity tracker daemon that runs on the host machine.

This must run OUTSIDE Docker to access local applications.
"""

import asyncio
import argparse
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic.tracking.aggregator import ActivityAggregator


async def main(
    data_dir: str = "./data/activity",
    api_port: int = 8001,
) -> None:
    """Run the activity tracker daemon."""
    print(f"🔍 Starting Activity Tracker...")
    print(f"   Data directory: {data_dir}")
    print(f"   API port: {api_port}")
    
    # Initialize aggregator
    aggregator = ActivityAggregator(
        data_dir=data_dir,
        enable_browser=True,
        enable_window=True,
        enable_vscode=True,
    )
    
    # Setup shutdown handler
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()
    
    def handle_signal():
        print("\n🛑 Shutting down...")
        shutdown_event.set()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)
    
    # Start tracking
    await aggregator.start()
    print("✅ Activity tracking started")
    print("   Tracking: Browser history, Active windows, VS Code files")
    print("   Press Ctrl+C to stop\n")
    
    # Optional: Start a simple API server for the main assistant to query
    from aiohttp import web
    
    async def handle_context(request):
        """Return current activity context."""
        context = await aggregator.get_current_context()
        return web.json_response(context)
    
    async def handle_summary(request):
        """Return activity summary."""
        hours = int(request.query.get("hours", 1))
        from datetime import timedelta
        summary = aggregator.get_summary(
            since=datetime.now() - timedelta(hours=hours),
        )
        return web.json_response({
            "text": summary.to_natural_language(),
            "total_events": summary.total_events,
            "active_minutes": summary.active_duration_seconds / 60,
            "top_apps": summary.top_applications,
            "files": summary.files_worked_on[:10],
            "searches": summary.searches_performed[:10],
        })
    
    async def handle_events(request):
        """Return recent events."""
        limit = int(request.query.get("limit", 50))
        events = aggregator.get_events(limit=limit)
        return web.json_response([e.to_dict() for e in events])
    
    async def handle_health(request):
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "tracking": True,
            "trackers": [t.name for t in aggregator.trackers if t.is_running],
        })
    
    app = web.Application()
    app.router.add_get("/context", handle_context)
    app.router.add_get("/summary", handle_summary)
    app.router.add_get("/events", handle_events)
    app.router.add_get("/health", handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", api_port)
    await site.start()
    print(f"📡 Activity API running on http://127.0.0.1:{api_port}")
    
    # Run until shutdown
    try:
        while not shutdown_event.is_set():
            # Print periodic status
            await asyncio.sleep(60)
            summary = aggregator.get_summary()
            if summary.total_events > 0:
                print(f"[{datetime.now().strftime('%H:%M')}] Events: {summary.total_events}, "
                      f"Active: {summary.active_duration_seconds/60:.1f}m")
    except asyncio.CancelledError:
        pass
    finally:
        await aggregator.stop()
        await runner.cleanup()
        print("✅ Activity tracker stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Activity Tracker Daemon")
    parser.add_argument("--data-dir", default="./data/activity", help="Data storage directory")
    parser.add_argument("--port", type=int, default=8001, help="API port")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(
            data_dir=args.data_dir,
            api_port=args.port,
        ))
    except KeyboardInterrupt:
        pass
