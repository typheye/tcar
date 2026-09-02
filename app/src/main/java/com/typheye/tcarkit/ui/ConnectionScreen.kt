package com.typheye.tcarkit.ui

import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.FocusInteraction
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.typheye.tcarkit.ConnectionState
import kotlinx.coroutines.launch

@Composable
internal fun ConnectionScreen(state: ConnectionState, onConnect: (String, String) -> Unit) {
    var username by rememberSaveable { mutableStateOf("tcar") }
    var password by rememberSaveable { mutableStateOf("admin123") }
    var dismissedFailure by rememberSaveable { mutableStateOf<String?>(null) }
    val busy = state is ConnectionState.Discovering
    val context = LocalContext.current
    val rootView = LocalView.current
    var passwordField by remember { mutableStateOf<EditText?>(null) }
    val submit = {
        if (!busy && username.isNotBlank() && password.isNotEmpty()) {
            rootView.findFocus()?.clearFocus()
            context.getSystemService(InputMethodManager::class.java)
                ?.hideSoftInputFromWindow(rootView.windowToken, 0)
            dismissedFailure = null
            onConnect(username.trim(), password)
        }
    }

    Box(Modifier.fillMaxSize().background(Color(0xFF0B0D10)), contentAlignment = Alignment.Center) {
        Column(
            Modifier.windowInsetsPadding(WindowInsets.safeDrawing).widthIn(max = 380.dp)
                .padding(horizontal = 24.dp, vertical = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("tCarKit", style = MaterialTheme.typography.headlineSmall, color = Color.White)
            NativeLoginField(
                value = username,
                onValueChange = { username = it },
                hint = "Username",
                imeAction = EditorInfo.IME_ACTION_NEXT,
                enabled = !busy,
                onEditorAction = {
                    passwordField?.requestFocus()
                    passwordField?.let {
                        context.getSystemService(InputMethodManager::class.java)
                            ?.showSoftInput(it, InputMethodManager.SHOW_IMPLICIT)
                    }
                },
            )
            NativeLoginField(
                value = password,
                onValueChange = { password = it },
                hint = "Password",
                password = true,
                imeAction = EditorInfo.IME_ACTION_DONE,
                enabled = !busy,
                onViewCreated = { passwordField = it },
                onEditorAction = submit,
            )
            Button(
                onClick = submit,
                enabled = !busy && username.isNotBlank() && password.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().height(48.dp),
            ) {
                if (busy) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                } else {
                    Text("Connect")
                }
            }
        }

        val failure = state as? ConnectionState.Failed
        if (failure != null && failure.message != dismissedFailure) {
            ConnectionErrorDialog(failure.message) { dismissedFailure = failure.message }
        }
    }
}

@Composable
private fun ConnectionErrorDialog(message: String, onDismiss: () -> Unit) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(dismissOnBackPress = true, dismissOnClickOutside = true),
    ) {
        Surface(
            color = Color(0xFF171A1F),
            contentColor = Color.White,
            shape = RoundedCornerShape(8.dp),
            tonalElevation = 8.dp,
            shadowElevation = 16.dp,
            modifier = Modifier.widthIn(min = 320.dp, max = 420.dp),
        ) {
            Column {
                Row(
                    modifier = Modifier.padding(start = 24.dp, top = 22.dp, end = 24.dp, bottom = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Box(
                        Modifier.size(42.dp).background(Color(0x26FF6A00), CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(Icons.Default.ErrorOutline, null, tint = MaterialTheme.colorScheme.primary)
                    }
                    Text("Connection failed", style = MaterialTheme.typography.titleLarge)
                }
                Text(
                    message,
                    color = Color(0xFFCED1D6),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp),
                )
                HorizontalDivider(Modifier.padding(top = 22.dp), color = Color(0xFF30343B))
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.End,
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("OK", color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
    }
}

@Composable
private fun NativeLoginField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    imeAction: Int,
    enabled: Boolean,
    password: Boolean = false,
    onViewCreated: (EditText) -> Unit = {},
    onEditorAction: () -> Unit,
) {
    val currentOnValueChange by rememberUpdatedState(onValueChange)
    val currentOnEditorAction by rememberUpdatedState(onEditorAction)
    val interactionSource = remember { MutableInteractionSource() }
    val coroutineScope = rememberCoroutineScope()
    var focusInteraction by remember { mutableStateOf<FocusInteraction.Focus?>(null) }

    Box(Modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = value,
            onValueChange = {},
            label = { Text(hint) },
            enabled = enabled,
            readOnly = true,
            singleLine = true,
            visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
            interactionSource = interactionSource,
            modifier = Modifier.fillMaxWidth(),
        )
        AndroidView(
            factory = { context ->
                EditText(context).apply {
                    background = null
                    alpha = 0f
                    isCursorVisible = false
                    setSingleLine(true)
                    inputType = InputType.TYPE_CLASS_TEXT or if (password) {
                        InputType.TYPE_TEXT_VARIATION_PASSWORD
                    } else {
                        InputType.TYPE_TEXT_VARIATION_NORMAL
                    }
                    this.imeOptions = imeAction and EditorInfo.IME_FLAG_NO_EXTRACT_UI.inv()
                    setText(value)
                    setSelection(value.length)
                    addTextChangedListener(object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                            currentOnValueChange(s?.toString().orEmpty())
                        }
                        override fun afterTextChanged(s: Editable?) = Unit
                    })
                    setOnFocusChangeListener { _, hasFocus ->
                        if (hasFocus) {
                            FocusInteraction.Focus().also { focus ->
                                focusInteraction = focus
                                coroutineScope.launch { interactionSource.emit(focus) }
                            }
                        } else {
                            focusInteraction?.let { focus ->
                                coroutineScope.launch {
                                    interactionSource.emit(FocusInteraction.Unfocus(focus))
                                }
                            }
                            focusInteraction = null
                        }
                    }
                    setOnEditorActionListener { _, actionId, _ ->
                        if (actionId == imeAction || actionId == EditorInfo.IME_ACTION_UNSPECIFIED) {
                            currentOnEditorAction()
                            true
                        } else {
                            false
                        }
                    }
                    onViewCreated(this)
                }
            },
            update = { field ->
                field.isEnabled = enabled
                if (field.text.toString() != value) {
                    field.setText(value)
                    field.setSelection(value.length)
                }
            },
            modifier = Modifier.matchParentSize(),
        )
    }
}
