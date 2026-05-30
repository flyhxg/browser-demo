<template>
  <div id="app">
    <nav>
      <router-link to="/">Home</router-link>
      <router-link to="/settings">Settings</router-link>
    </nav>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #fafafa;
  color: #333;
}
nav {
  display: flex;
  gap: 16px;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
}
nav a {
  text-decoration: none;
  color: #555;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
}
nav a:hover { background: #f0f0f0; }
nav a.router-link-active { color: #4a9eff; }
main { min-height: calc(100vh - 50px); }
</style>
