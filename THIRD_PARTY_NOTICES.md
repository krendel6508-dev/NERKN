# Исходные проекты и сторонние компоненты

NERKN — простая оболочка, объединяющая [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) и [tg-ws-proxy](https://github.com/Flowseal/tg-ws-proxy) от Flowseal. Интерфейс и управление ими находятся в `main.py`; встроенные исходные компоненты сохраняют своё авторство.

- `proxy/` — код Telegram-прокси Flowseal. Оригинальная MIT-лицензия и указание авторства сохранены в [proxy/LICENSE](proxy/LICENSE).
- `zapretes/`, `lists/`, `utils/` и `bin/` — поставляемые с проектом стратегии, списки и бинарные компоненты zapret. У Flowseal опубликованы [исходная лицензия и сведения о включённых бинарных файлах](https://github.com/Flowseal/zapret-discord-youtube/blob/main/LICENSE.txt).
- `WinDivert.dll`, `WinDivert64.sys`, `cygwin1.dll` и `winws.exe` — сторонние бинарные компоненты. Сведения об источниках и условиях WinDivert приведены в лицензии исходного zapret-проекта.
- Python-зависимости перечислены в `requirements.txt` и `requirements-build.txt`; их лицензии поставляются соответствующими пакетами.

В [README автора NERKN](README.md) указано условие об отсутствии монетизации исходного кода оболочки и его изменений. Оно не изменяет условия лицензий Flowseal, bol-van, WinDivert и других авторов. При распространении сторонних файлов сохраняйте их сведения об авторстве и лицензии.
