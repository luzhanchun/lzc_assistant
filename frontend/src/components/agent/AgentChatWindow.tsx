/**
 * Agent Chat Window Component
 * Main chat area with message display and empty state for Agent mode
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { Message } from '../../types';
import { AgentMessageBubble } from './AgentMessageBubble';

export interface AgentChatWindowProps {
    messages: Message[];
    isLoading: boolean;
    onSuggestionClick?: (text: string) => void;
    error?: string | null;
    isToolSelectorOpen?: boolean;
}

export function AgentChatWindow({ messages, isLoading, error }: AgentChatWindowProps) {
    messages = messages.filter(
        (message) =>
        (message.role === 'user' || message.role === 'assistant') && 
        ((message.content !== null && message.content !== undefined && message.content !== '') || message.trace !== undefined)
    )
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isNearBottom, setIsNearBottom] = useState(true);
    const [isUserScrolling, setIsUserScrolling] = useState(false);
    const prevMessagesLengthRef = useRef(messages.length);

    // Check if user is near the bottom of the scroll container
    const checkIsNearBottom = useCallback(() => {
        const container = scrollContainerRef.current;
        if (!container) return true;

        const { scrollTop, scrollHeight, clientHeight } = container;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        return distanceFromBottom < 100;
    }, []);

    // Handle scroll events to track user interaction
    const handleScroll = useCallback(() => {
        if (!isUserScrolling) {
            setIsUserScrolling(true);
            // Reset user scrolling flag after a short delay
            setTimeout(() => setIsUserScrolling(false), 1000);
        }
        setIsNearBottom(checkIsNearBottom());
    }, [isUserScrolling, checkIsNearBottom]);

    // Force scroll to bottom when user sends a new message
    useEffect(() => {
        const prevLength = prevMessagesLengthRef.current;
        const currentLength = messages.length;

        // Check if a new user message was added
        if (currentLength > prevLength && messages.length > 0) {
            const lastMessage = messages[messages.length - 1];
            // If the new message is from user, force scroll to bottom
            if (lastMessage.role === 'user') {
                messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }
        }

        prevMessagesLengthRef.current = currentLength;
    }, [messages]);

    // Auto-scroll to bottom when new messages arrive, but only if user is near bottom
    useEffect(() => {
        if (isNearBottom && !isUserScrolling && messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isNearBottom, isUserScrolling]);

    // Set up scroll event listener
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (container) {
            container.addEventListener('scroll', handleScroll, { passive: true });
            return () => container.removeEventListener('scroll', handleScroll);
        }
    }, [handleScroll]);

    // Initialize near bottom state
    useEffect(() => {
        setIsNearBottom(checkIsNearBottom());
    }, [checkIsNearBottom]);

    const isEmpty = messages.length === 0;

    return (
        <div
            ref={scrollContainerRef}
            className={`
        flex-1 p-4 md:p-6
        bg-gradient-to-b from-white to-gray-50 dark:from-gray-900 dark:to-gray-950
        ${isEmpty ? 'overflow-y-hidden' : 'overflow-y-auto'}
      `}
        >
            {isEmpty ? (
                <EmptyState />
            ) : (
                <div className="max-w-3xl mx-auto w-full">
                    {messages
                    .map((message) => (
                        <AgentMessageBubble key={message.id} message={message} hasError={!!error} />
                    ))}

                    {/* Loading indicator */}
                    {isLoading &&
                        messages.length > 0 &&
                        messages[messages.length - 1].role === 'user' && (
                            <LoadingIndicator />
                        )}
                </div>
            )}
            {!isEmpty && <div ref={messagesEndRef} className="h-4" />}
        </div>
    );
}

/**
 * Empty state for Agent mode
 */
function EmptyState() {
    return (
        <div className="flex flex-col items-center justify-center h-full w-full text-gray-500 dark:text-gray-400 animate-in fade-in duration-500 overflow-x-hidden px-4 box-border">
            <section className="empty-state-hero relative flex-1 flex flex-col items-center justify-center overflow-hidden">
                <div className="relative group w-full px-4">
                    <div className="w-full h-48 max-w-5xl mx-auto flex items-center justify-center">
                        <img
                            src="/image.png"
                            alt="CookHero Logo"
                            className="w-full max-w-4xl object-contain transition-all duration-500 group-hover:scale-105"
                        />
                    </div>
                </div>
            </section>
        </div>
    );
}

/**
 * Loading indicator when waiting for response
 */
function LoadingIndicator() {
    return (
        <div className="flex gap-4 mb-6">
            <div className="w-10 h-10 rounded-xl bg-orange-500 flex items-center justify-center shrink-0 shadow-sm">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="space-y-2 pt-2">
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <span className="animate-pulse">Agent is thinking...</span>
                </div>
            </div>
        </div>
    );
}
