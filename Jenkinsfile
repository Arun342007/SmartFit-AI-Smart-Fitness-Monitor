// ---------------------------------------------------------------------
// Jenkinsfile - CI/CD pipeline for the Smart Fitness Health Monitor
//
// Stages: Checkout -> Install Dependencies -> Run Tests -> Build Docker
//         Image -> Run/Validate Docker Container -> (optional) Push to
//         Docker Hub
//
// Docker Hub credentials are only read in the optional push stage, from a
// Jenkins "Username with password" credential (Manage Jenkins >
// Credentials) with the ID DOCKERHUB_CREDENTIALS_ID below. Nothing secret
// is hard-coded here, and the pipeline runs fine without the credential
// when PUSH_TO_DOCKERHUB is left unticked.
// ---------------------------------------------------------------------

pipeline {
    agent any

    parameters {
        booleanParam(name: 'PUSH_TO_DOCKERHUB', defaultValue: false,
                     description: 'Push the built image to Docker Hub (needs the credential below)')
    }

    environment {
        IMAGE_NAME             = "smart-fitness-health"
        CONTAINER_NAME         = "smart-fitness-health-ci"
        DOCKERHUB_REPO         = "yourdockerhubusername/smart-fitness-health" // update before use
        DOCKERHUB_CREDENTIALS_ID = "dockerhub-credentials"                   // Jenkins credential ID
    }

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {

        stage('Checkout') {
            steps {
                echo 'Checking out source code from GitHub...'
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                echo 'Creating a virtual environment and installing core dependencies...'
                // requirements.txt is the core set; the webcam packages
                // (requirements-camera.txt) are not needed for CI.
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }

        stage('Run Tests') {
            steps {
                echo 'Running automated pytest test suite...'
                sh '''
                    . venv/bin/activate
                    pytest --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                echo 'Building Docker image...'
                sh 'docker build -t ${IMAGE_NAME}:${BUILD_NUMBER} -t ${IMAGE_NAME}:latest .'
            }
        }

        stage('Run/Validate Docker Container') {
            steps {
                echo 'Running the container and validating the health-check endpoint...'
                // No host port is published, so this cannot clash with another
                // service on the agent; the check runs inside the container.
                sh '''
                    docker rm -f ${CONTAINER_NAME} || true
                    docker run -d --name ${CONTAINER_NAME} ${IMAGE_NAME}:${BUILD_NUMBER}
                    for i in $(seq 1 20); do
                        if docker exec ${CONTAINER_NAME} python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/api/health-check').read().decode())"; then
                            exit 0
                        fi
                        echo "Waiting for the app to start ($i/20)..."
                        sleep 3
                    done
                    docker logs ${CONTAINER_NAME}
                    exit 1
                '''
            }
        }

        stage('Push to Docker Hub') {
            when {
                expression { return params.PUSH_TO_DOCKERHUB }
            }
            steps {
                echo 'Logging into Docker Hub securely using Jenkins credentials...'
                withCredentials([usernamePassword(credentialsId: env.DOCKERHUB_CREDENTIALS_ID,
                                                  usernameVariable: 'DH_USER',
                                                  passwordVariable: 'DH_PASS')]) {
                    sh '''
                        echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                        docker tag ${IMAGE_NAME}:${BUILD_NUMBER} ${DOCKERHUB_REPO}:${BUILD_NUMBER}
                        docker tag ${IMAGE_NAME}:latest ${DOCKERHUB_REPO}:latest
                        docker push ${DOCKERHUB_REPO}:${BUILD_NUMBER}
                        docker push ${DOCKERHUB_REPO}:latest
                        docker logout
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Cleaning up the validation container...'
            sh 'docker rm -f ${CONTAINER_NAME} || true'
        }
        success {
            echo '✅ Pipeline completed successfully.'
        }
        failure {
            echo '❌ Pipeline failed. Check the console output above.'
        }
    }
}
