import { useAuthStore } from '../stores/auth';
export async function* streamChat(conversationId, message) {
    const auth = useAuthStore();
    const resp = await fetch('/api/chat/send', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${auth.token}`,
        },
        body: JSON.stringify({
            user_id: auth.userId,
            conversation_id: conversationId,
            message,
        }),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ message: 'SSE error' }));
        throw new Error(err.detail?.message || err.message || 'SSE error');
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done)
            break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        let currentEvent = '';
        for (const line of lines) {
            if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim();
            }
            else if (line.startsWith('data: ')) {
                const raw = line.slice(6);
                try {
                    yield { event: currentEvent, data: JSON.parse(raw) };
                }
                catch {
                    // ignore unparseable lines
                }
            }
        }
    }
}
export async function* streamChatNew(messages) {
    // Used from HomeView where no conversation exists yet;
    // conversation is created by the backend on first message.
    // Actually, we create it ourselves first.
    throw new Error('Use createConversation + streamChat instead');
}
