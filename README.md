docker build -t localhost:5000/loyalty_app:latest .
docker push localhost:5000/loyalty_app:latest
docker service update --image localhost:5000/loyalty_app:latest --force loyalty_app_app