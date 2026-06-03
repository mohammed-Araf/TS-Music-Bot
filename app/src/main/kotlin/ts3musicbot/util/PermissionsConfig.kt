package ts3musicbot.util

import java.io.File

class PermissionsConfig {
    var enabled: Boolean = false
    var requiredBadges: List<String> = emptyList()
    var requiredServerGroups: List<Int> = emptyList()
    var cacheBadges: Boolean = true
    var cacheTtlSeconds: Int = 300
    var denyMessage: String = "You are not allowed to use music commands."
    var publicCommands: List<String> = listOf("np", "q", "src", "ping")

    companion object {
        fun load(file: File): PermissionsConfig {
            val config = PermissionsConfig()
            println("[PERMISSIONS] Loading permissions configuration from: ${file.absolutePath}")
            if (!file.exists()) {
                println("[PERMISSIONS] Permissions file does not exist at: ${file.absolutePath}. Using default disabled config.")
                return config
            }
            
            var currentKey = ""
            
            file.forEachLine { rawLine ->
                val line = rawLine.trim()
                if (line.isEmpty() || line.startsWith("#")) return@forEachLine
                
                if (line.endsWith(":")) {
                    currentKey = line.substringBefore(":").trim()
                    return@forEachLine
                }
                
                if (line.startsWith("-")) {
                    val value = line.substring(1).trim().replace("\"", "").replace("'", "")
                    if (currentKey == "required_badges") {
                        config.requiredBadges = config.requiredBadges + value
                    } else if (currentKey == "required_server_groups") {
                        val intVal = value.toIntOrNull()
                        if (intVal != null) {
                            config.requiredServerGroups = config.requiredServerGroups + intVal
                        }
                    } else if (currentKey == "public_commands") {
                        config.publicCommands = config.publicCommands + value
                    }
                    return@forEachLine
                }
                
                val parts = line.split(":", limit = 2)
                if (parts.size == 2) {
                    val key = parts[0].trim()
                    val value = parts[1].trim()
                    currentKey = key
                    
                    val cleanValue = value.replace("\"", "").replace("'", "")
                    
                    when (key) {
                        "enabled" -> config.enabled = cleanValue.lowercase() == "true"
                        "cache_badges" -> config.cacheBadges = cleanValue.lowercase() == "true"
                        "cache_ttl_seconds" -> config.cacheTtlSeconds = cleanValue.toIntOrNull() ?: 300
                        "deny_message" -> config.denyMessage = value.removeSurrounding("\"").removeSurrounding("'")
                        "required_badges" -> {
                            if (cleanValue.isNotEmpty() && cleanValue != "[]") {
                                config.requiredBadges = cleanValue.removeSurrounding("[", "]").split(",").map { it.trim() }.filter { it.isNotEmpty() }
                            }
                        }
                        "required_server_groups" -> {
                            if (cleanValue.isNotEmpty() && cleanValue != "[]") {
                                config.requiredServerGroups = cleanValue.removeSurrounding("[", "]").split(",").mapNotNull { it.trim().toIntOrNull() }
                            }
                        }
                        "public_commands" -> {
                            if (cleanValue.isNotEmpty() && cleanValue != "[]") {
                                config.publicCommands = cleanValue.removeSurrounding("[", "]").split(",").map { it.trim() }.filter { it.isNotEmpty() }
                            }
                        }
                    }
                }
            }
            println("[PERMISSIONS] Config loaded successfully: enabled=${config.enabled}, badges=${config.requiredBadges}, groups=${config.requiredServerGroups}, publicCommands=${config.publicCommands}, denyMessage=\"${config.denyMessage}\"")
            return config
        }
    }
}
