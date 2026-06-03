<template>
  <div id="app">
    <aside class="sidebar">
      <div class="sidebar-logo">
        <span class="logo-icon">AI</span>
        <span class="logo-text">Agent</span>
      </div>
      <nav class="sidebar-nav">
        <router-link to="/" class="nav-item" :class="{ active: $route.path === '/' }">
          <span class="nav-icon">💬</span>
          <span class="nav-text">Chat</span>
        </router-link>
        <router-link to="/trading" class="nav-item" :class="{ active: $route.path === '/trading' }">
          <span class="nav-icon">📈</span>
          <span class="nav-text">Trading</span>
        </router-link>
        <router-link to="/workflow" class="nav-item" :class="{ active: $route.path === '/workflow' }">
          <span class="nav-icon">⚡</span>
          <span class="nav-text">Workflow</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <span class="footer-text">AI Trading Agent v1.0</span>
      </div>
    </aside>
    <main class="main-content">
      <div class="router-wrapper">
        <router-view />
      </div>
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #0a0a0f;
  color: #e4e4e7;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
#app {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.sidebar {
  width: 220px;
  background: #111114;
  border-right: 1px solid #1e1e24;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.sidebar-logo {
  padding: 24px 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid #1e1e24;
}
.logo-icon {
  width: 32px;
  height: 32px;
  background: #6366f1;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}
.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.5px;
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  gap: 4px;
  flex: 1;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 10px;
  color: #71717a;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
}
.nav-item:hover {
  background: #1a1a1f;
  color: #e4e4e7;
}
.nav-item.active {
  background: rgba(99, 102, 241, 0.15);
  color: #6366f1;
  font-weight: 600;
}
.nav-icon {
  font-size: 18px;
  line-height: 1;
  width: 24px;
  text-align: center;
}
.nav-text {
  line-height: 1;
}
.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid #1e1e24;
}
.footer-text {
  font-size: 11px;
  color: #52525b;
  letter-spacing: 0.5px;
}
.main-content {
  flex: 1;
  overflow: hidden;
  min-width: 0;
  background: #0a0a0f;
  display: flex;
  flex-direction: column;
}
.router-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>