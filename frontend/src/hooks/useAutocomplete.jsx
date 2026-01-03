import { useState, useRef, useCallback } from 'react';
import axios from 'axios';

export function useAutocomplete() {
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const autocompleteTimeout = useRef(null);

  const fetchSuggestions = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    try {
      const response = await axios.post('/api/autocomplete/history', {
        query,
        limit: 5
      });

      if (response.data.success && response.data.suggestions.length > 0) {
        setSuggestions(response.data.suggestions);
        setShowSuggestions(true);
        setSelectedIndex(-1);
      } else {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    } catch (err) {
      console.error('Autocomplete error:', err);
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, []);

  const handleQueryChange = useCallback((newQuery, callback) => {
    // Clear previous timeout
    if (autocompleteTimeout.current) {
      clearTimeout(autocompleteTimeout.current);
    }

    // Call the callback immediately (update state)
    callback(newQuery);

    // Debounce autocomplete fetch
    autocompleteTimeout.current = setTimeout(() => {
      fetchSuggestions(newQuery);
    }, 300);
  }, [fetchSuggestions]);

  const handleKeyDown = useCallback((e, currentQuery, onSelect) => {
    if (!showSuggestions || suggestions.length === 0) return false;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        return true;

      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : -1);
        return true;

      case 'Enter':
        if (selectedIndex >= 0) {
          e.preventDefault();
          onSelect(suggestions[selectedIndex]);
          setShowSuggestions(false);
          setSelectedIndex(-1);
          return true;
        }
        break;

      case 'Escape':
        setShowSuggestions(false);
        setSelectedIndex(-1);
        return true;

      case 'Tab':
        if (selectedIndex >= 0) {
          e.preventDefault();
          onSelect(suggestions[selectedIndex]);
          setShowSuggestions(false);
          setSelectedIndex(-1);
          return true;
        }
        break;
    }

    return false;
  }, [showSuggestions, suggestions, selectedIndex]);

  const selectSuggestion = useCallback((suggestion, onSelect) => {
    onSelect(suggestion);
    setShowSuggestions(false);
    setSelectedIndex(-1);
  }, []);

  const hideSuggestions = useCallback(() => {
    setShowSuggestions(false);
    setSelectedIndex(-1);
  }, []);

  return {
    suggestions,
    showSuggestions,
    selectedIndex,
    handleQueryChange,
    handleKeyDown,
    selectSuggestion,
    hideSuggestions
  };
}