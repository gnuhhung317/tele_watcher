"""Test script to check access to private Telegram channels."""

import asyncio
import os
from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, ChannelInvalidError

async def test_channel_access():
    """Test access to the specified channel."""
    
    # Your credentials from .env
    api_id = 21660012
    api_hash = "14db52d23d543f002a99af1b89776a90"
    session_name = "watcher"
    
    # Channel ID from URL (both formats)
    channel_ids = [
        -1789266730,  # With minus prefix
        1789266730,   # Without minus prefix
        "1789266730", # As string
        "-1789266730" # As string with minus
    ]
    
    client = TelegramClient(session_name, api_id, api_hash)
    
    try:
        print("🔐 Connecting to Telegram...")
        await client.start()
        
        me = await client.get_me()
        print(f"✅ Connected as: {me.first_name} (@{me.username})")
        
        print("\n🔍 Testing channel access...")
        
        for channel_id in channel_ids:
            try:
                print(f"\n📡 Testing channel ID: {channel_id}")
                
                # Try to get entity
                entity = await client.get_entity(channel_id)
                print(f"✅ Found: {entity.title}")
                print(f"   Type: {type(entity).__name__}")
                print(f"   ID: {entity.id}")
                print(f"   Access Hash: {entity.access_hash}")
                
                # Try to get recent messages
                messages = await client.get_messages(entity, limit=5)
                print(f"✅ Can read messages: {len(messages)} messages found")
                
                if messages:
                    latest = messages[0]
                    print(f"   Latest message: {latest.date}")
                    print(f"   Text preview: {(latest.text or 'No text')[:50]}...")
                
                print(f"✅ Channel {channel_id} is accessible!")
                break
                
            except ChannelPrivateError:
                print(f"❌ Channel {channel_id}: Private channel, no access")
                
            except ChannelInvalidError:
                print(f"❌ Channel {channel_id}: Invalid channel ID")
                
            except Exception as e:
                print(f"❌ Channel {channel_id}: Error - {e}")
        
        print("\n📋 Listing all accessible dialogs...")
        dialogs = await client.get_dialogs(limit=20)
        
        channels = []
        for dialog in dialogs:
            if hasattr(dialog.entity, 'broadcast') or hasattr(dialog.entity, 'megagroup'):
                channels.append({
                    'name': dialog.name,
                    'id': dialog.entity.id,
                    'type': 'Channel' if getattr(dialog.entity, 'broadcast', False) else 'Group'
                })
        
        print(f"Found {len(channels)} channels/groups:")
        for ch in channels:
            print(f"  - {ch['name']} (ID: {ch['id']}, Type: {ch['type']})")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 If you see 'EOF when reading a line', you need to create session first:")
        print("   python create_session.py")
        
    finally:
        await client.disconnect()
        print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_channel_access())