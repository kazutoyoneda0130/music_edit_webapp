import { loginUrl } from '../api/client'

export function LoginPage() {
  return (
    <div className="login-page">
      <div className="login-icon">♪</div>
      <h1>BPM解析 / 複数曲クロスフェード連結ツール</h1>
      <p>このアプリを利用するには、許可されたGoogleアカウントでログインしてください。</p>
      <a className="login-button" href={loginUrl()}>
        Googleでログイン
      </a>
    </div>
  )
}
