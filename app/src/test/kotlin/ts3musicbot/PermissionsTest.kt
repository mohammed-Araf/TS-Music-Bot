package ts3musicbot

import ts3musicbot.chat.ChatReader
import ts3musicbot.chat.ChatUpdate
import ts3musicbot.chat.ChatUpdateListener
import ts3musicbot.chat.CommandListener
import ts3musicbot.chat.UserPermissionCache
import ts3musicbot.client.Client
import ts3musicbot.util.BotSettings
import ts3musicbot.util.MainConfig
import ts3musicbot.util.CommandsConfig
import ts3musicbot.util.ProvidersConfig
import ts3musicbot.util.PermissionsConfig
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class PermissionsTest {

    class TestClient(botSettings: BotSettings) : Client(botSettings) {
        val messagesSent = mutableListOf<String>()
        override fun sendMsgToChannel(message: String) {
            messagesSent.add(message)
        }
    }

    private fun setupPermissions() {
        BotSettings.main = MainConfig()
        BotSettings.commands = CommandsConfig().apply {
            prefix = "!"
            commands = mapOf(
                "play" to "p",
                "skip" to "s",
                "ping" to "ping"
            )
        }
        BotSettings.providers = ProvidersConfig()
        BotSettings.permissions = PermissionsConfig().apply {
            permissions.enabled = true
            permissions.requiredBadges = listOf("vip", "admin")
            permissions.requiredServerGroups = listOf(10, 20)
            permissions.cacheTtlSeconds = 300
            permissions.denyMessage = "ACCESS DENIED"
            permissions.publicCommands = listOf("ping")
        }
    }

    @Test
    fun testPublicCommandBypassesPermissions() {
        setupPermissions()
        val client = TestClient(BotSettings())
        val reader = ChatReader(
            client = client,
            botSettings = BotSettings(),
            onChatUpdateListener = object : ChatUpdateListener {
                override fun onChatUpdated(update: ChatUpdate) {}
            },
            commandListener = object : CommandListener {
                override fun onCommandExecuted(command: String, output: String, extra: Any?) {}
                override fun onCommandProgress(command: String, output: String, extra: Any?) {}
            }
        )

        // Clear cache and ensure no cached entries exist for user 100
        reader.permissionsCache.clear()

        // invokerId=100 with NO badges/groups, issuing public command !ping
        reader.parseLine("!ping", invokerId = 100)

        // It should bypass and not send "ACCESS DENIED"
        assertFalse(client.messagesSent.contains("ACCESS DENIED"))
    }

    @Test
    fun testNonPublicCommandDeniedWithoutPermissions() {
        setupPermissions()
        val client = TestClient(BotSettings())
        val reader = ChatReader(
            client = client,
            botSettings = BotSettings(),
            onChatUpdateListener = object : ChatUpdateListener {
                override fun onChatUpdated(update: ChatUpdate) {}
            },
            commandListener = object : CommandListener {
                override fun onCommandExecuted(command: String, output: String, extra: Any?) {}
                override fun onCommandProgress(command: String, output: String, extra: Any?) {}
            }
        )

        // User 100 has NO permissions in cache, and the client query isn't running so fallback is empty
        reader.permissionsCache.clear()

        reader.parseLine("!play Song Name", invokerId = 100)

        // It should send deny message
        assertTrue(client.messagesSent.contains("ACCESS DENIED"))
    }

    @Test
    fun testNonPublicCommandAllowedWithBadge() {
        setupPermissions()
        val client = TestClient(BotSettings())
        val reader = ChatReader(
            client = client,
            botSettings = BotSettings(),
            onChatUpdateListener = object : ChatUpdateListener {
                override fun onChatUpdated(update: ChatUpdate) {}
            },
            commandListener = object : CommandListener {
                override fun onCommandExecuted(command: String, output: String, extra: Any?) {}
                override fun onCommandProgress(command: String, output: String, extra: Any?) {}
            }
        )

        // Cache the vip badge for user 100
        reader.permissionsCache[100] = UserPermissionCache(
            badges = listOf("vip"),
            serverGroups = emptyList(),
            cachedAt = System.currentTimeMillis()
        )

        reader.parseLine("!play Song Name", invokerId = 100)

        // It should NOT deny
        assertFalse(client.messagesSent.contains("ACCESS DENIED"))
    }

    @Test
    fun testNonPublicCommandAllowedWithServerGroup() {
        setupPermissions()
        val client = TestClient(BotSettings())
        val reader = ChatReader(
            client = client,
            botSettings = BotSettings(),
            onChatUpdateListener = object : ChatUpdateListener {
                override fun onChatUpdated(update: ChatUpdate) {}
            },
            commandListener = object : CommandListener {
                override fun onCommandExecuted(command: String, output: String, extra: Any?) {}
                override fun onCommandProgress(command: String, output: String, extra: Any?) {}
            }
        )

        // Cache the server group 10 for user 100
        reader.permissionsCache[100] = UserPermissionCache(
            badges = emptyList(),
            serverGroups = listOf(10),
            cachedAt = System.currentTimeMillis()
        )

        reader.parseLine("!play Song Name", invokerId = 100)

        // It should NOT deny
        assertFalse(client.messagesSent.contains("ACCESS DENIED"))
    }

    @Test
    fun testAliasCommandMapping() {
        setupPermissions()
        val client = TestClient(BotSettings())
        val reader = ChatReader(
            client = client,
            botSettings = BotSettings(),
            onChatUpdateListener = object : ChatUpdateListener {
                override fun onChatUpdated(update: ChatUpdate) {}
            },
            commandListener = object : CommandListener {
                override fun onCommandExecuted(command: String, output: String, extra: Any?) {}
                override fun onCommandProgress(command: String, output: String, extra: Any?) {}
            }
        )

        // Check that "!p" maps to "play". Since user has no permission, it should deny "play"
        reader.permissionsCache.clear()
        reader.parseLine("!p Song Name", invokerId = 100)

        assertTrue(client.messagesSent.contains("ACCESS DENIED"))
    }
}
