import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold text-white">
            AI Trading Navigator
          </h1>
        </header>
        <main className="p-6">
          <p className="text-gray-400">Dashboard coming soon...</p>
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
