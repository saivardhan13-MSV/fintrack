// CI/CD pipeline: runs on every push (configure a Multibranch Pipeline or a GitHub webhook).
// Requires a Linux agent with Python 3.11+; the Docker stage also needs Docker on the agent.
pipeline {
    agent any

    options {
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PYTHONDONTWRITEBYTECODE = '1'
    }

    stages {
        stage('Install') {
            steps {
                sh '''
                    python3 -m venv .venv
                    .venv/bin/pip install -q -r requirements-dev.txt
                '''
            }
        }

        stage('Lint') {
            steps {
                sh '.venv/bin/ruff check .'
            }
        }

        stage('Type check') {
            steps {
                sh '.venv/bin/mypy fintrack'
            }
        }

        stage('Test') {
            steps {
                sh '''
                    mkdir -p reports
                    .venv/bin/pytest \
                        --junitxml=reports/junit.xml \
                        --cov-report=xml:reports/coverage.xml \
                        --cov-fail-under=90
                '''
            }
        }

        stage('Build Docker image') {
            when { branch 'main' }
            steps {
                sh 'docker build -t fintrack:${BUILD_NUMBER} -t fintrack:latest .'
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'reports/junit.xml'
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
        }
        failure {
            echo 'Build failed: check the stage logs above for the failing lint, type or test step.'
        }
    }
}
