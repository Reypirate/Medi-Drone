//  todo: migrate to next themes

import { ThemeProvider as NextThemesProvider, useTheme as useNextTheme } from 'next-themes';
import React from 'react';

export function ThemeProvider({ children, ...props }: React.ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}

export const useTheme = () => {
  const context = useNextTheme();
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
