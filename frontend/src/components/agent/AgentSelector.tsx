/**
 * Agent selector for choosing which agent handles the current chat request.
 */

import { useCallback, useEffect, useState } from 'react';
import { Bot, Loader2 } from 'lucide-react';
import type { AgentInfo } from '../../types';
import { getRegisteredAgents } from '../../services/api/agent';
import { DEFAULT_AGENT_NAME, getAgentDisplayName } from '../../constants';

export interface AgentSelectorProps {
  token?: string;
  value: string;
  onChange: (agentName: string) => void;
  onAgentsLoaded?: (agentNames: string[]) => void;
  disabled?: boolean;
}

export function AgentSelector({
  token,
  value,
  onChange,
  onAgentsLoaded,
  disabled = false,
}: AgentSelectorProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    if (!token) {
      setAgents([]);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const response = await getRegisteredAgents(token);
      setAgents(response.agents);
      onAgentsLoaded?.(response.agents.map(agent => agent.name));
    } catch (err) {
      console.error('Failed to load registered agents:', err);
      setError(err instanceof Error ? err.message : 'Failed to load agents');
    } finally {
      setIsLoading(false);
    }
  }, [onAgentsLoaded, token]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    if (agents.length === 0) return;

    const hasSelectedAgent = agents.some(agent => agent.name === value);
    if (!hasSelectedAgent) {
      const defaultAgent = agents.find(agent => agent.name === DEFAULT_AGENT_NAME);
      onChange((defaultAgent ?? agents[0]).name);
    }
  }, [agents, value, onChange]);

  const selectedAgent = agents.find(agent => agent.name === value);
  const isFallbackTriageSelected = (selectedAgent?.name ?? value) === DEFAULT_AGENT_NAME;

  return (
    <div className="mt-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-end">
      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        {isLoading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Bot className="w-3.5 h-3.5" />
        )}
        <span>Agent</span>
      </div>

      <select
        value={selectedAgent?.name ?? value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || isLoading || agents.length === 0}
        title={selectedAgent?.description}
        className={`min-w-40 max-w-full px-2 py-1.5 text-sm text-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed ${
          isFallbackTriageSelected
            ? 'text-emerald-600 dark:text-emerald-400 font-medium'
            : 'text-gray-700 dark:text-gray-200'
        }`}
      >
        {agents.length === 0 ? (
          <option value={value}>{isLoading ? 'Loading...' : getAgentDisplayName(value)}</option>
        ) : (
          agents.map(agent => (
            <option
              key={agent.name}
              value={agent.name}
              className={
                agent.name === DEFAULT_AGENT_NAME
                  ? 'text-emerald-600'
                  : 'text-gray-700'
              }
            >
              {getAgentDisplayName(agent.name)}
            </option>
          ))
        )}
      </select>

      {error && (
        <span className="text-xs text-red-500 dark:text-red-400 sm:max-w-60 truncate">
          {error}
        </span>
      )}
    </div>
  );
}
