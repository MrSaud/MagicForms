package com.magicforms.mobile.ui.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.magicforms.mobile.data.models.ApiEntity

@Composable
fun OrganizationLoginField(
    entitySlug: String,
    onEntitySlugChange: (String) -> Unit,
    username: String,
    onUsernameChange: (String) -> Unit,
    directoryEntities: List<ApiEntity>,
    modifier: Modifier = Modifier,
) {
    val showEntitySegment = directoryEntities.isNotEmpty()

    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = "Organization username",
            style = MaterialTheme.typography.titleSmall,
        )

        Surface(
            shape = RoundedCornerShape(12.dp),
            color = MaterialTheme.colorScheme.surfaceVariant,
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (showEntitySegment) {
                    EntitySlugSegment(
                        entitySlug = entitySlug,
                        onEntitySlugChange = onEntitySlugChange,
                        directoryEntities = directoryEntities,
                        modifier = Modifier.weight(1f),
                    )
                    Text(
                        text = "–",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 8.dp),
                    )
                }
                TextField(
                    value = username,
                    onValueChange = onUsernameChange,
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("username") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.None,
                        autoCorrect = false,
                    ),
                    colors = entityFieldColors(),
                )
            }
        }

        if (showEntitySegment) {
            Text(
                text = when {
                    directoryEntities.size > 1 ->
                        "Type your organization slug or tap the list to choose one, then enter your username."
                    directoryEntities.size == 1 ->
                        "Organization slug (e.g. ${directoryEntities.first().slug}), then your username — same as the web sign-in."
                    else ->
                        "Organization slug and username, separated by a hyphen."
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun EntitySlugSegment(
    entitySlug: String,
    onEntitySlugChange: (String) -> Unit,
    directoryEntities: List<ApiEntity>,
    modifier: Modifier = Modifier,
) {
    var menuExpanded by remember { mutableStateOf(false) }

    Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
        TextField(
            value = entitySlug,
            onValueChange = onEntitySlugChange,
            modifier = Modifier.weight(1f),
            placeholder = { Text("org-slug") },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodyLarge.copy(fontFamily = FontFamily.Monospace),
            keyboardOptions = KeyboardOptions(
                capitalization = KeyboardCapitalization.None,
                autoCorrect = false,
            ),
            colors = entityFieldColors(),
        )
        if (directoryEntities.size > 1) {
            IconButton(onClick = { menuExpanded = true }) {
                Icon(
                    imageVector = Icons.Default.List,
                    contentDescription = "Choose organization",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                directoryEntities.forEach { entity ->
                    DropdownMenuItem(
                        text = { Text("${entity.name} (${entity.slug})") },
                        onClick = {
                            onEntitySlugChange(entity.slug)
                            menuExpanded = false
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun entityFieldColors() = TextFieldDefaults.colors(
    focusedContainerColor = androidx.compose.ui.graphics.Color.Transparent,
    unfocusedContainerColor = androidx.compose.ui.graphics.Color.Transparent,
    disabledContainerColor = androidx.compose.ui.graphics.Color.Transparent,
    focusedIndicatorColor = androidx.compose.ui.graphics.Color.Transparent,
    unfocusedIndicatorColor = androidx.compose.ui.graphics.Color.Transparent,
)
