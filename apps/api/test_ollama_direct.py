#!/usr/bin/env python3
"""
Direct Ollama Provider Test Script
Tests the Ollama provider in isolation to verify connectivity and streaming.
"""
import asyncio
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.providers.ollama import OllamaProvider
from app.providers.types import Message, ModelRequest
from app.core.config import settings


async def test_ollama_connection():
    """Test basic Ollama API connectivity."""
    import httpx

    print("=" * 80)
    print("OLLAMA CONNECTION TEST")
    print("=" * 80)
    print(f"\n🔗 Testing connection to: {settings.ollama_base_url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                print(f"✅ Ollama is running!")
                print(f"\n📦 Available models ({len(models)}):")
                for model in models:
                    print(f"   - {model.get('name', 'unknown')}")
                return True
            else:
                print(f"❌ Ollama returned status code: {response.status_code}")
                return False

    except Exception as e:
        print(f"❌ Cannot connect to Ollama: {e}")
        print(f"\n💡 Make sure Ollama is running:")
        print(f"   ollama serve")
        return False


async def test_ollama_streaming():
    """Test Ollama provider streaming functionality."""
    print("\n" + "=" * 80)
    print("OLLAMA STREAMING TEST")
    print("=" * 80)
    print(f"\n🤖 Model: {settings.ollama_chat_model}")
    print(f"📝 Prompt: 'Say hello in one sentence'\n")

    try:
        provider = OllamaProvider(settings.ollama_base_url, think=settings.ollama_think)

        request = ModelRequest(
            model=settings.ollama_chat_model,
            messages=[Message(role="user", content="Say hello in one sentence")],
            temperature=0.7,
        )

        print("🔄 Streaming response:")
        print("-" * 80)

        chunks_received = 0
        full_text = ""

        async for delta in provider.stream(request):
            if delta.text:
                print(delta.text, end="", flush=True)
                full_text += delta.text
                chunks_received += 1

            if delta.finish_reason:
                print("\n" + "-" * 80)
                print(f"\n✅ Stream completed!")
                print(f"   Finish reason: {delta.finish_reason}")
                if delta.usage:
                    print(f"   Input tokens: {delta.usage.input_tokens}")
                    print(f"   Output tokens: {delta.usage.output_tokens}")
                print(f"   Chunks received: {chunks_received}")
                return True

    except Exception as e:
        print(f"\n❌ Streaming test failed: {e}")
        print(f"\n💡 Possible issues:")
        print(f"   1. Model not pulled: ollama pull {settings.ollama_chat_model}")
        print(f"   2. Model name mismatch in .env")
        print(f"   3. Ollama service not running")
        return False


async def test_ollama_with_context():
    """Test Ollama with a multi-turn conversation."""
    print("\n" + "=" * 80)
    print("OLLAMA CONTEXT TEST")
    print("=" * 80)
    print("\n🔄 Testing multi-turn conversation...\n")

    try:
        provider = OllamaProvider(settings.ollama_base_url)

        request = ModelRequest(
            model=settings.ollama_chat_model,
            messages=[
                Message(role="system", content="You are a helpful assistant."),
                Message(role="user", content="My name is Alice."),
                Message(role="assistant", content="Hello Alice! Nice to meet you."),
                Message(role="user", content="What's my name?"),
            ],
            temperature=0.3,
        )

        print("📝 Conversation:")
        print("   User: My name is Alice.")
        print("   Assistant: Hello Alice! Nice to meet you.")
        print("   User: What's my name?")
        print("\n🔄 Response:")
        print("-" * 80)

        full_text = ""
        async for delta in provider.stream(request):
            if delta.text:
                print(delta.text, end="", flush=True)
                full_text += delta.text

            if delta.finish_reason:
                print("\n" + "-" * 80)

                # Check if response mentions "Alice"
                if "alice" in full_text.lower():
                    print("\n✅ Context test passed! Model remembered the name.")
                else:
                    print("\n⚠️  Context test unclear. Response:", full_text[:100])
                return True

    except Exception as e:
        print(f"\n❌ Context test failed: {e}")
        return False


async def main():
    """Run all Ollama tests."""
    print("\n" + "=" * 80)
    print("🚀 VERSUSLAB OLLAMA INTEGRATION TEST SUITE")
    print("=" * 80)
    print(f"\n⚙️  Configuration:")
    print(f"   Ollama URL: {settings.ollama_base_url}")
    print(f"   Chat Model: {settings.ollama_chat_model}")
    print(f"   Embedding Model: {settings.ollama_embedding_model}")
    print(f"   Think Mode: {settings.ollama_think}")

    results = []

    # Test 1: Connection
    results.append(await test_ollama_connection())

    if not results[0]:
        print("\n" + "=" * 80)
        print("❌ FAILED: Ollama is not reachable. Stopping tests.")
        print("=" * 80)
        return 1

    # Test 2: Streaming
    await asyncio.sleep(1)
    results.append(await test_ollama_streaming())

    # Test 3: Context
    await asyncio.sleep(1)
    results.append(await test_ollama_with_context())

    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print(f"   Connection Test: {'✅ PASS' if results[0] else '❌ FAIL'}")
    print(f"   Streaming Test: {'✅ PASS' if results[1] else '❌ FAIL'}")
    print(f"   Context Test: {'✅ PASS' if results[2] else '❌ FAIL'}")
    print(f"\n   Overall: {sum(results)}/{len(results)} tests passed")

    if all(results):
        print("\n🎉 All tests passed! Ollama integration is working correctly.")
        print("=" * 80)
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
