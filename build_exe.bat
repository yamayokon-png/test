@echo off
echo ========================================
echo  Marker Tracker - exe ビルドスクリプト
echo ========================================

echo.
echo [1/3] 必要なパッケージをインストール中...
pip install opencv-python numpy matplotlib pillow pyinstaller

echo.
echo [2/3] exe をビルド中...
pyinstaller --onefile --windowed --name "MarkerTracker" track_marker_app.py

echo.
echo [3/3] 完了！
echo dist\MarkerTracker.exe が作成されました。
echo そのファイルをダブルクリックで起動できます。
echo.
pause
